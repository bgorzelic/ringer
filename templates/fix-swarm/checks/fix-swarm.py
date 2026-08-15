#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


MAX_SUMMARY_WORDS = 700
SUMMARY_HEADINGS = ("Summary", "Files Changed", "Verification", "Assumptions")
OPEN_PLACEHOLDER = "{" * 2
CLOSE_PLACEHOLDER = "}" * 2

# Only these headings terminate a section extraction.
HEADING_ALTERNATION = "|".join(re.escape(heading) for heading in SUMMARY_HEADINGS)


def fail(name: str, detail: str) -> str:
    return f"FAIL [{name}]: {detail}"


def has_placeholder(value: str) -> bool:
    return OPEN_PLACEHOLDER in value or CLOSE_PLACEHOLDER in value


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def output_tail(text: str, limit: int = 4000) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[-limit:]


def run_shell(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def parse_owned_files(raw: str) -> list[str]:
    normalized = raw.replace("\\n", "\n").replace(";", "\n").replace(",", "\n")
    paths: list[str] = []
    for line in normalized.splitlines():
        item = line.strip().strip("'\"")
        if not item:
            continue
        if item.startswith("./"):
            item = item[2:]
        paths.append(item.rstrip("/"))
    return paths


def allowed(path: str, owned: list[str]) -> bool:
    if "*" in owned:
        return True
    clean = path[2:] if path.startswith("./") else path
    for item in owned:
        if clean == item or clean.startswith(item.rstrip("/") + "/"):
            return True
    return False


def section(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$([\s\S]*?)"
        rf"(?=^##\s+(?:{HEADING_ALTERNATION})\s*$|\Z)",
        re.IGNORECASE | re.MULTILINE,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def validate_summary(summary_path: Path) -> tuple[str, list[str]]:
    failures: list[str] = []
    if not summary_path.is_file():
        return "", [fail("missing_summary", f"{summary_path} does not exist")]
    if summary_path.stat().st_size == 0:
        return "", [fail("empty_summary", f"{summary_path} is empty")]

    text = summary_path.read_text(encoding="utf-8", errors="replace")
    if word_count(text) > MAX_SUMMARY_WORDS:
        failures.append(fail("summary_too_long", f"summary has more than {MAX_SUMMARY_WORDS} words"))
    if not re.search(r"^#\s+Fix Summary\s*$", text, re.IGNORECASE | re.MULTILINE):
        failures.append(fail("missing_title", "fix-summary.md must start with '# Fix Summary'"))
    for heading in SUMMARY_HEADINGS:
        if not re.search(rf"^##\s+{re.escape(heading)}\s*$", text, re.IGNORECASE | re.MULTILINE):
            failures.append(fail("missing_summary_section", f"fix-summary.md missing '## {heading}'"))
        elif not section(text, heading):
            failures.append(fail("empty_summary_section", f"fix-summary.md '## {heading}' has no content"))
    return text, failures


def atomic_publish(final_path: Path, content: str) -> None:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(final_path.parent), prefix=f".{final_path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        tmp_path.replace(final_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fix verification and export a checked patch.")
    parser.add_argument("--verify-command", required=True)
    parser.add_argument("--patch", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--exported-summary", required=True, type=Path)
    parser.add_argument("--owned-files", required=True)
    args = parser.parse_args()

    failures: list[str] = []
    for name, value in (
        ("verify_command", args.verify_command),
        ("patch", str(args.patch)),
        ("exported_summary", str(args.exported_summary)),
        ("owned_files", args.owned_files),
    ):
        if has_placeholder(value):
            failures.append(fail("placeholder_unfilled", f"{name} still contains an unfilled placeholder"))

    owned_files = parse_owned_files(args.owned_files)
    if not owned_files:
        failures.append(fail("missing_owned_files", "owned-files list is empty"))

    summary_text, summary_failures = validate_summary(args.summary)
    failures.extend(summary_failures)

    if not has_placeholder(args.verify_command):
        verify = run_shell(args.verify_command)
        if verify.returncode != 0:
            failures.append(
                fail(
                    "verify_command_failed",
                    f"command exited {verify.returncode}: {args.verify_command}\n{output_tail(verify.stdout)}",
                )
            )

    add_result = run_git(["add", "-A"])
    if add_result.returncode != 0:
        failures.append(fail("git_add_failed", output_tail(add_result.stdout)))

    if not args.summary.is_absolute() and args.summary.exists():
        run_git(["reset", "--quiet", "--", str(args.summary)])

    names_result = run_git(["diff", "--cached", "--name-only", "-z"])
    changed_files = [item for item in names_result.stdout.split("\0") if item]
    if names_result.returncode != 0:
        failures.append(fail("git_diff_names_failed", output_tail(names_result.stdout)))
    elif not changed_files:
        failures.append(fail("empty_patch", "no staged changes were produced"))
    else:
        for changed in changed_files:
            if not allowed(changed, owned_files):
                failures.append(fail("outside_owned_files", f"{changed} is not in the owned-files list"))

    patch_result = run_git(["diff", "--cached", "--binary"])
    patch_content = patch_result.stdout
    if patch_result.returncode != 0:
        failures.append(fail("git_diff_failed", output_tail(patch_result.stdout)))
    elif not patch_content.strip():
        failures.append(fail("patch_not_written", "no patch content was produced"))

    if failures:
        for item in failures:
            print(item)
        return 1

    try:
        atomic_publish(args.patch, patch_content)
        atomic_publish(args.exported_summary, summary_text)
    except OSError as exc:
        print(fail("export_failed", f"failed to publish exports: {exc}"))
        return 1

    print(f"PASS [fix_contract]: exported {args.patch} with {len(changed_files)} changed file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
