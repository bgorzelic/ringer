#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


MAX_WORDS = 1200
REQUIRED_HEADINGS = ("Summary", "Findings", "Clean", "Assumptions")
FINDING_FIELDS = ("Evidence:", "Impact:", "Fix:", "Priority:", "Confidence:")
OPEN_PLACEHOLDER = "{" * 2
CLOSE_PLACEHOLDER = "}" * 2

# The canonical, accepted finding heading: '### Finding: <neutral summary>'.
CANONICAL_FINDING_HEADING_RE = re.compile(r"^###\s+Finding:", re.IGNORECASE)

# Loosely recognizes a line that is plausibly *meant* to be a finding heading
# even when malformed (wrong heading level, numbered, bulleted, bold-only,
# missing colon, etc.), so a malformed heading no longer hides its block and
# the block's own field defects from being reported in the same run.
FINDING_HEADING_CANDIDATE_RE = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]*)?(?:[-*+][ \t]+)?(?:\d+[.)][ \t]*)?\**[ \t]*Finding\b.*$",
    re.IGNORECASE | re.MULTILINE,
)

# Only these headings terminate a section extraction. A malformed level-2
# '## Finding: ...' block is not a canonical heading, so it stays inside the
# Findings region instead of prematurely closing it.
CANONICAL_HEADING_PATTERN = "|".join(re.escape(heading) for heading in REQUIRED_HEADINGS)


def fail(name: str, detail: str) -> str:
    return f"FAIL [{name}]: {detail}"


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def has_heading(text: str, heading: str) -> bool:
    return bool(re.search(rf"^##\s+{re.escape(heading)}\s*$", text, re.IGNORECASE | re.MULTILINE))


def section(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$([\s\S]*?)"
        rf"(?=^##\s+(?:{CANONICAL_HEADING_PATTERN})\s*$|\Z)",
        re.IGNORECASE | re.MULTILINE,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def split_finding_blocks(findings: str) -> list[str]:
    starts = [match.start() for match in FINDING_HEADING_CANDIDATE_RE.finditer(findings)]
    if not starts:
        return []
    starts.append(len(findings))
    return [findings[starts[i] : starts[i + 1]] for i in range(len(starts) - 1)]


def field_line_values(block: str, field: str) -> list[str]:
    """Values of lines that are EXACTLY the given field label (e.g. 'Evidence:')
    at the start of the line, not prose that merely mentions the label."""
    pattern = re.compile(rf"^[ \t]*{re.escape(field)}[ \t]*(.*)$", re.IGNORECASE | re.MULTILINE)
    return [match.group(1).strip() for match in pattern.finditer(block)]


def validate_finding_block(block: str, index: int) -> list[str]:
    failures: list[str] = []
    heading_line = block.splitlines()[0].strip() if block.splitlines() else ""
    heading_match = CANONICAL_FINDING_HEADING_RE.match(heading_line)
    if not heading_match:
        failures.append(
            fail(
                "finding_bad_heading",
                f"finding {index} heading must be exactly '### Finding: <neutral summary>' "
                f"(found: {heading_line!r})",
            )
        )
    elif not heading_line[heading_match.end():].strip():
        failures.append(
            fail(
                "finding_empty_title",
                f"finding {index} heading must include a nonempty summary after 'Finding:'",
            )
        )

    for field in FINDING_FIELDS:
        values = field_line_values(block, field)
        if not values:
            failures.append(fail("finding_missing_field", f"finding {index} is missing {field}"))
        elif len(values) > 1:
            failures.append(fail("finding_duplicate_field", f"finding {index} has more than one {field} line"))
        elif not values[0]:
            failures.append(fail("finding_empty_field", f"finding {index} {field} has no value"))

    if "Evidence:" in block and not re.search(r"\b[\w./-]+:\d+\b", block):
        failures.append(fail("finding_missing_line", f"finding {index} evidence should cite file:line"))
    if not re.search(r"Priority:\s*P[0-3]\b", block, re.IGNORECASE):
        failures.append(fail("finding_bad_priority", f"finding {index} priority must be P0, P1, P2, or P3"))
    if not re.search(r"Confidence:\s*(high|medium|low)\b", block, re.IGNORECASE):
        failures.append(fail("finding_bad_confidence", f"finding {index} confidence must be high, medium, or low"))
    return failures


def validate_report(path: Path, surface: str) -> list[str]:
    failures: list[str] = []
    if not path.is_file():
        return [fail("missing_report", f"{path} does not exist")]
    if path.stat().st_size == 0:
        return [fail("empty_report", f"{path} is empty")]

    text = path.read_text(encoding="utf-8", errors="replace")
    if word_count(text) > MAX_WORDS:
        failures.append(fail("too_long", f"report has more than {MAX_WORDS} words"))
    if not re.search(r"^#\s+Review Report\s*$", text, re.IGNORECASE | re.MULTILINE):
        failures.append(fail("missing_title", "report must start with '# Review Report'"))
    for heading in REQUIRED_HEADINGS:
        if not has_heading(text, heading):
            failures.append(fail("missing_section", f"missing '## {heading}'"))

    summary = section(text, "Summary")
    if not summary:
        failures.append(fail("summary_empty", "Summary section has no content"))
    summary_lines = [line for line in summary.splitlines() if line.strip()]
    if len(summary_lines) > 3:
        failures.append(fail("summary_too_long", "Summary must be no more than 3 non-empty lines"))

    findings = section(text, "Findings")
    if not findings:
        failures.append(fail("missing_findings_body", "Findings section has no content"))
    else:
        blocks = split_finding_blocks(findings)
        if blocks:
            for index, block in enumerate(blocks, start=1):
                failures.extend(validate_finding_block(block, index))
        elif "no findings" not in findings.lower():
            failures.append(fail("findings_not_explicit", "Findings must contain at least one '### Finding:' block or say 'No findings'"))

    clean = section(text, "Clean")
    if not clean:
        failures.append(fail("clean_not_explicit", "Clean section must name at least one reviewed dimension with no findings"))

    assumptions = section(text, "Assumptions")
    if not assumptions:
        failures.append(fail("assumptions_empty", "Assumptions section has no content"))

    if OPEN_PLACEHOLDER in surface or CLOSE_PLACEHOLDER in surface:
        failures.append(fail("placeholder_unfilled", "surface placeholder was not filled in the check command"))
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a review-swarm report contract.")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--surface", required=True)
    args = parser.parse_args()

    failures = validate_report(args.report, args.surface)
    if failures:
        for item in failures:
            print(item)
        return 1
    print(f"PASS [review_contract]: {args.report} is structured and evidence-ready for {args.surface}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
