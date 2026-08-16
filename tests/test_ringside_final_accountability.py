#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DASHBOARD_HTML = ROOT / "dashboard" / "dashboard.html"
NODE = shutil.which("node")


def _extract_function(script: str, name: str) -> str:
    match = re.search(rf"function {re.escape(name)}\(", script)
    assert match, f"expected a top-level function named {name}"
    start = match.start()
    brace_start = script.index("{", match.end())
    depth = 0
    for index in range(brace_start, len(script)):
        char = script[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return script[start : index + 1]
    raise AssertionError(f"could not find closing brace for function {name}")


def _extract_const(script: str, name: str) -> str:
    match = re.search(rf"const {re.escape(name)} = [^;]+;", script)
    assert match, f"expected a top-level const named {name}"
    return match.group(0)


class RingsideFinalAccountabilityTests(unittest.TestCase):
    """Covers the second round of accountability fields (tokens_unknown/tokens_partial,
    access_class/access_label, and the local model tier threshold) with a mix of real
    Node execution of the extracted pure functions (so numeric edge cases like the
    exact 2/3 first-try rate are proven, not assumed) and source-level static checks
    (so wiring into the DOM-touching render functions can't silently regress)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.html = DASHBOARD_HTML.read_text(encoding="utf-8")
        script_match = re.search(r"<script>(.*)</script>", cls.html, re.S)
        assert script_match, "dashboard.html must contain an inline <script> block"
        cls.script = script_match.group(1)

        # Assemble a standalone, DOM-free bundle of the pure functions under test so
        # they can be executed for real via Node instead of only pattern-matched.
        pieces = [
            _extract_function(cls.script, "numberOrZero"),
            _extract_function(cls.script, "isUnknownAmount"),
            _extract_function(cls.script, "isTokensUnknown"),
            _extract_function(cls.script, "isTokensPartial"),
            _extract_function(cls.script, "formatTokens"),
            _extract_function(cls.script, "formatCount"),
            _extract_function(cls.script, "optionalMetaLabel"),
            _extract_function(cls.script, "accessLabel"),
            _extract_function(cls.script, "blockedLabel"),
            _extract_function(cls.script, "escapeHtml"),
            _extract_const(cls.script, "PROVEN_MIN_TASKS"),
            _extract_const(cls.script, "PROVEN_MIN_FIRST_TRY_PASS_RATE"),
            _extract_function(cls.script, "localTier"),
        ]
        cls.pure_bundle = "\n".join(pieces)

    # -- helpers ----------------------------------------------------------------

    def _call(self, fn_name: str, *args):
        """Executes fn_name(*args) inside a real Node process against the bundle of
        functions extracted straight from dashboard.html, and returns the JSON result."""
        if NODE is None:
            self.skipTest("node executable not available")
        script = (
            self.pure_bundle
            + "\n"
            + f"const __args = JSON.parse(process.argv[2]);\n"
            + f"const __result = {fn_name}(...__args);\n"
            + "process.stdout.write(JSON.stringify(__result === undefined ? null : __result));\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as handle:
            handle.write(script)
            path = handle.name
        try:
            completed = subprocess.run(
                [NODE, path, json.dumps(list(args))],
                capture_output=True,
                text=True,
                timeout=10,
            )
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertEqual(
            completed.returncode,
            0,
            f"node execution of {fn_name} failed: {completed.stderr}",
        )
        return json.loads(completed.stdout)

    # -- tokens_unknown / tokens_partial (executable) ---------------------------

    def test_tokens_unknown_flag_wins_even_with_a_numeric_value_present(self) -> None:
        self.assertTrue(self._call("isTokensUnknown", {"tokens_unknown": True}, 4200))

    def test_tokens_unknown_false_falls_back_to_legacy_null_check(self) -> None:
        self.assertTrue(self._call("isTokensUnknown", {"tokens_unknown": False}, None))
        self.assertFalse(self._call("isTokensUnknown", {"tokens_unknown": False}, 10))

    def test_tokens_unknown_defaults_to_legacy_check_when_flag_missing(self) -> None:
        # Field entirely absent (an older Ringer server) must behave exactly as before:
        # unknown iff the numeric value itself is null/undefined/empty.
        self.assertTrue(self._call("isTokensUnknown", {}, None))
        self.assertFalse(self._call("isTokensUnknown", {}, 500))

    def test_tokens_partial_requires_the_flag_and_a_known_value(self) -> None:
        self.assertTrue(self._call("isTokensPartial", {"tokens_partial": True}, 500))
        self.assertFalse(self._call("isTokensPartial", {"tokens_partial": False}, 500))
        self.assertFalse(self._call("isTokensPartial", {}, 500))

    def test_tokens_partial_is_suppressed_when_also_unknown(self) -> None:
        # unknown always outranks partial: a total can't be simultaneously "no data"
        # and "some data, incomplete".
        self.assertFalse(
            self._call(
                "isTokensPartial",
                {"tokens_unknown": True, "tokens_partial": True},
                4200,
            )
        )

    def test_format_tokens_unknown_ignores_numeric_value(self) -> None:
        self.assertEqual(self._call("formatTokens", 99999, True, False), "tok unknown")

    def test_format_tokens_partial_appends_marker_without_hiding_the_number(self) -> None:
        self.assertEqual(self._call("formatTokens", 4200, False, True), "4,200 tok (partial)")

    def test_format_tokens_known_renders_plain_total(self) -> None:
        self.assertEqual(self._call("formatTokens", 4200, False, False), "4,200 tok")

    def test_format_tokens_missing_legacy_fields_render_unknown_not_zero(self) -> None:
        # A task/run object with none of tokens/tokens_unknown/tokens_partial set --
        # the true "missing legacy fields" case -- must read as unknown, never as 0.
        unknown = self._call("isTokensUnknown", {}, None)
        partial = self._call("isTokensPartial", {}, None)
        self.assertEqual(self._call("formatTokens", None, unknown, partial), "tok unknown")

    # -- access_class / access_label (executable) --------------------------------

    def test_access_label_combines_class_and_optional_label(self) -> None:
        self.assertEqual(
            self._call("accessLabel", {"access_class": "byok", "access_label": "Personal Pro"}),
            "byok — Personal Pro",
        )

    def test_access_label_omits_dash_when_label_absent(self) -> None:
        self.assertEqual(self._call("accessLabel", {"access_class": "byok"}), "byok")

    def test_access_label_falls_back_to_legacy_access_field(self) -> None:
        self.assertEqual(self._call("accessLabel", {"access": "subscription"}), "subscription")

    def test_access_label_null_when_nothing_configured(self) -> None:
        self.assertIsNone(self._call("accessLabel", {}))

    def test_access_label_never_infers_from_engine_or_other_fields(self) -> None:
        # A task carrying engine/model info but no explicit access_class/access/label
        # must not have access "inferred" -- accountability requires it stay null.
        self.assertIsNone(self._call("accessLabel", {"engine": "codex", "model": "gpt-5"}))

    # -- malicious text: returned verbatim, safety delegated to textContent -----

    def test_access_label_passes_malicious_text_through_unescaped(self) -> None:
        malicious = "<img src=x onerror=alert(1)>"
        self.assertEqual(
            self._call("accessLabel", {"access_class": malicious}),
            malicious,
        )

    def test_blocked_reason_passes_malicious_text_through_unescaped(self) -> None:
        malicious = "\"><script>alert(1)</script>"
        self.assertEqual(
            self._call("blockedLabel", {"blocked_reason": malicious}),
            f"blocked: {malicious}",
        )

    def test_blocked_kind_and_reason_both_pass_malicious_text_through_unescaped(self) -> None:
        malicious_kind = "<img src=x onerror=alert(2)>"
        malicious_reason = "\"><script>alert(1)</script>"
        self.assertEqual(
            self._call(
                "blockedLabel",
                {"blocked_kind": malicious_kind, "blocked_reason": malicious_reason},
            ),
            f"blocked ({malicious_kind}): {malicious_reason}",
        )

    def test_escape_html_neutralizes_the_same_malicious_payloads(self) -> None:
        malicious = "<img src=x onerror=alert(1)>&\"'"
        escaped = self._call("escapeHtml", malicious)
        for token in ("<", ">", '"', "'", "&"):
            if token == "&":
                continue
            self.assertNotIn(token, escaped)
        self.assertIn("&lt;img", escaped)

    def test_blocked_reason_empty_string_still_labeled_not_dropped(self) -> None:
        self.assertEqual(self._call("blockedLabel", {"blocked_reason": ""}), "blocked: unknown")

    def test_blocked_reason_absent_is_null(self) -> None:
        self.assertIsNone(self._call("blockedLabel", {}))

    # -- blockedLabel: legacy vs. kind-aware forms (executable) -----------------

    def test_blocked_label_both_fields_absent_is_null(self) -> None:
        # No blocking info reported at all -- nothing renders, layout is preserved.
        self.assertIsNone(self._call("blockedLabel", {}))

    def test_blocked_label_legacy_payload_with_only_reason_uses_conservative_form(self) -> None:
        # An older Ringer server that never reported blocked_kind must keep reading as
        # the plain "blocked: reason" form it always used.
        self.assertEqual(
            self._call("blockedLabel", {"blocked_reason": "Worker timed out."}),
            "blocked: Worker timed out.",
        )

    def test_blocked_label_every_blocked_kind_matches_terminal_static_form(self) -> None:
        # Mirrors ringer.py's worker_blocked_reason()/blocked_accounting_text() pairing
        # for every BlockedKind so the live dashboard matches the terminal/static report.
        kind_reasons = {
            "configuration": "Worker configuration prevented this task from starting.",
            "preparation": "Task preparation failed.",
            "spawn": "Worker process could not be started.",
            "cancelled": "Task was cancelled before completion.",
            "runner": "Runner stopped before task completion.",
        }
        for kind, reason in kind_reasons.items():
            with self.subTest(blocked_kind=kind):
                self.assertEqual(
                    self._call(
                        "blockedLabel",
                        {"blocked_kind": kind, "blocked_reason": reason},
                    ),
                    f"blocked ({kind}): {reason}",
                )

    def test_blocked_label_kind_present_reason_missing_reads_unknown(self) -> None:
        # A present blocked_kind with no reason must still read as unknown, not vanish
        # or silently drop the kind information that is known.
        self.assertEqual(
            self._call("blockedLabel", {"blocked_kind": "spawn"}),
            "blocked (spawn): unknown",
        )

    def test_blocked_label_kind_present_but_empty_reads_unknown(self) -> None:
        self.assertEqual(
            self._call("blockedLabel", {"blocked_kind": "", "blocked_reason": "x"}),
            "blocked (unknown): x",
        )

    def test_blocked_label_both_present_but_empty_read_unknown(self) -> None:
        self.assertEqual(
            self._call("blockedLabel", {"blocked_kind": "", "blocked_reason": ""}),
            "blocked (unknown): unknown",
        )

    def test_blocked_label_never_infers_kind_from_reason_prose(self) -> None:
        # blocked_reason text that looks like it embeds a kind (parenthetical, "kind="
        # markers, etc.) must never be parsed into a kind -- only an explicit
        # blocked_kind field can produce the parenthetical form.
        sneaky_reason = "blocked (spawn): kind=configuration injected into reason text"
        self.assertEqual(
            self._call("blockedLabel", {"blocked_reason": sneaky_reason}),
            f"blocked: {sneaky_reason}",
        )

    # -- local tier threshold: proven only at >=3 tasks and >=0.67 first-try ----

    def test_exact_two_thirds_first_try_rate_is_below_threshold(self) -> None:
        # 2 passes out of 3 attempts is 0.6666...; float precision keeps it under the
        # 0.67 bar even though it rounds to "67%" for display. This is the case a
        # naive rounded-percent comparison would get wrong.
        self.assertEqual(
            self._call("localTier", {"tasks": 3, "first_try_pass_rate": 2 / 3}),
            "probation",
        )

    def test_first_try_rate_exactly_at_threshold_is_proven(self) -> None:
        self.assertEqual(
            self._call("localTier", {"tasks": 3, "first_try_pass_rate": 0.67}),
            "proven",
        )

    def test_just_under_threshold_is_probation(self) -> None:
        self.assertEqual(
            self._call("localTier", {"tasks": 10, "first_try_pass_rate": 0.6699}),
            "probation",
        )

    def test_high_pass_rate_with_too_few_tasks_is_probation(self) -> None:
        self.assertEqual(
            self._call("localTier", {"tasks": 2, "first_try_pass_rate": 1.0}),
            "probation",
        )

    def test_missing_first_try_pass_rate_is_probation(self) -> None:
        self.assertEqual(self._call("localTier", {"tasks": 5}), "probation")

    def test_server_claiming_proven_is_not_trusted_without_matching_metrics(self) -> None:
        # A row that arrives with tier: "proven" but insufficient tasks/rate must not
        # be displayed as proven -- the dashboard recomputes locally, it never trusts
        # the server's label outright.
        self.assertEqual(
            self._call(
                "localTier",
                {"tier": "proven", "tasks": 1, "first_try_pass_rate": 1.0},
            ),
            "probation",
        )

    def test_three_tasks_above_threshold_is_proven(self) -> None:
        self.assertEqual(
            self._call("localTier", {"tasks": 3, "first_try_pass_rate": 0.9}),
            "proven",
        )

    # -- static wiring: DOM-touching call sites use the accountable helpers -----

    def test_render_models_table_uses_local_tier_not_raw_row_tier(self) -> None:
        render_fn = self._extract_top_level_function("renderModelsTable")
        self.assertIn("const tier = localTier(row);", render_fn)
        self.assertNotIn("safeClass(row.tier", render_fn)
        self.assertNotIn("row.tier ||", render_fn)

    def test_local_tier_thresholds_are_named_constants(self) -> None:
        self.assertIn("const PROVEN_MIN_TASKS = 3;", self.script)
        self.assertIn("const PROVEN_MIN_FIRST_TRY_PASS_RATE = 0.67;", self.script)

    def test_update_task_record_computes_tokens_state_via_shared_helpers(self) -> None:
        update_fn = self._extract_top_level_function("updateTaskRecord")
        self.assertIn("const tokensUnknown = isTokensUnknown(task, task.tokens);", update_fn)
        self.assertIn("const tokensPartial = isTokensPartial(task, task.tokens);", update_fn)
        self.assertIn("formatTokens(tokens, tokensUnknown, tokensPartial)", update_fn)

    def test_normalize_payload_computes_run_tokens_state_via_shared_helpers(self) -> None:
        normalize_fn = self._extract_top_level_function("normalizePayload")
        self.assertIn("tokensUnknown: isTokensUnknown(run, rawTokens),", normalize_fn)
        self.assertIn("tokensPartial: isTokensPartial(run, rawTokens),", normalize_fn)

    def test_update_run_record_passes_partial_flag_through(self) -> None:
        update_run_fn = self._extract_top_level_function("updateRunRecord")
        self.assertIn("formatTokens(run.tokens, run.tokensUnknown, run.tokensPartial)", update_run_fn)

    def test_access_and_blocked_values_reach_the_dom_only_through_set_text(self) -> None:
        # setText assigns via .textContent (verified below), never via innerHTML, so
        # a malicious access_class/access_label/blocked_reason can only ever be
        # "assigned as text" -- it is structurally unable to execute as markup.
        set_text_fn = self._extract_top_level_function("setText")
        self.assertIn("node.textContent = text;", set_text_fn)

        update_fn = self._extract_top_level_function("updateTaskRecord")
        self.assertIn("setText(record.elements.access, taskAccess", update_fn)
        self.assertIn("setText(record.elements.blocked, blocked", update_fn)

        update_run_fn = self._extract_top_level_function("updateRunRecord")
        self.assertIn("setText(record.elements.access, runAccess", update_run_fn)

        drawer_fn = self._extract_top_level_function("updateDrawerContent")
        self.assertIn("setText(refs.blocked, blocked", drawer_fn)

    def test_missing_legacy_fields_do_not_crash_task_or_run_rendering(self) -> None:
        # Static guard: the accountability helpers used from updateTaskRecord /
        # normalizePayload only ever read optional-chained / nullish-coalesced
        # properties off task and run, so a legacy object missing every new field
        # is handled the same way it was rendered before this round.
        update_fn = self._extract_top_level_function("updateTaskRecord")
        self.assertIn("task.attempts", update_fn)
        self.assertIn("accessLabel(task)", update_fn)
        self.assertIn("blockedLabel(task)", update_fn)
        for fn_name in ("isTokensUnknown", "isTokensPartial", "accessLabel", "blockedLabel"):
            fn_src = self._extract_top_level_function(fn_name)
            self.assertIn("?.", fn_src, f"{fn_name} must optional-chain into its source object")
        # optionalMetaLabel takes the raw value directly (not a source object), so it
        # guards missing input with nullish coalescing instead of optional chaining.
        self.assertIn("??", self._extract_top_level_function("optionalMetaLabel"))

    # -- keyboard semantics regression guard (kept intact by this round) --------

    def test_task_cards_still_expose_button_role_and_keyboard_handlers(self) -> None:
        create_fn = self._extract_top_level_function("createTaskRecord")
        self.assertIn('node.setAttribute("role", "button")', create_fn)
        self.assertIn("node.tabIndex = 0", create_fn)
        keydown_match = re.search(
            r'node\.addEventListener\("keydown", event => \{(.*?)\}\);',
            create_fn,
            re.S,
        )
        self.assertIsNotNone(keydown_match, "createTaskRecord must still register a keydown handler")
        body = keydown_match.group(1)
        self.assertIn('event.key !== "Enter"', body)
        self.assertIn('event.key !== " "', body)
        self.assertIn("toggleTaskDrawer(runRecord, key)", body)

    # -- helpers ------------------------------------------------------------------

    def _extract_top_level_function(self, name: str) -> str:
        return _extract_function(self.script, name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
