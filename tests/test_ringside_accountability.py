#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DASHBOARD_HTML = ROOT / "dashboard" / "dashboard.html"


class RingsideAccountabilityTests(unittest.TestCase):
    """Static inspection of the shipped dashboard so accessibility and accountability
    semantics can't silently regress without a source (not headless-browser) change."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.html = DASHBOARD_HTML.read_text(encoding="utf-8")
        script_match = re.search(r"<script>(.*)</script>", cls.html, re.S)
        assert script_match, "dashboard.html must contain an inline <script> block"
        cls.script = script_match.group(1)

    # -- keyboard operability -------------------------------------------------

    def test_task_cards_get_button_role_and_tabindex(self) -> None:
        self.assertIn('node.setAttribute("role", "button")', self.script)
        self.assertIn("node.tabIndex = 0", self.script)

    def test_task_cards_skip_semantics_for_empty_placeholder(self) -> None:
        create_fn = self._extract_function("createTaskRecord")
        self.assertIn('if (key !== "__empty__")', create_fn)

    def test_task_cards_expose_aria_expanded(self) -> None:
        self.assertIn('node.setAttribute("aria-expanded", "false")', self.script)
        self.assertIn('setAttribute("aria-expanded", String(selected))', self.script)

    def test_aria_expanded_updates_on_open_and_close(self) -> None:
        render_open_drawer = self._extract_function("renderOpenDrawer")
        self.assertIn('setAttribute("aria-expanded", String(record === taskRecord))', render_open_drawer)
        close_drawer = self._extract_function("closeTaskDrawer")
        self.assertIn('setAttribute("aria-expanded", "false")', close_drawer)

    def test_task_cards_handle_enter_and_space_keys(self) -> None:
        create_fn = self._extract_function("createTaskRecord")
        keydown_match = re.search(
            r'node\.addEventListener\("keydown", event => \{(.*?)\}\);',
            create_fn,
            re.S,
        )
        self.assertIsNotNone(keydown_match, "createTaskRecord must register a keydown handler")
        body = keydown_match.group(1)
        self.assertIn('event.key !== "Enter"', body)
        self.assertIn('event.key !== " "', body)
        self.assertIn("event.preventDefault()", body)
        self.assertIn("toggleTaskDrawer(runRecord, key)", body)

    def test_keydown_handler_ignores_empty_placeholder_and_nested_controls(self) -> None:
        create_fn = self._extract_function("createTaskRecord")
        keydown_match = re.search(
            r'node\.addEventListener\("keydown", event => \{(.*?)\}\);',
            create_fn,
            re.S,
        )
        body = keydown_match.group(1)
        self.assertIn('if (key === "__empty__") return;', body)
        self.assertIn('event.target.closest("a, button, input, select, textarea")', body)

    def test_click_behavior_is_preserved(self) -> None:
        create_fn = self._extract_function("createTaskRecord")
        click_match = re.search(
            r'node\.addEventListener\("click", event => \{(.*?)\}\);',
            create_fn,
            re.S,
        )
        self.assertIsNotNone(click_match, "createTaskRecord must still register a click handler")
        body = click_match.group(1)
        self.assertIn('if (key === "__empty__") return;', body)
        self.assertIn("toggleTaskDrawer(runRecord, key)", body)

    def test_focus_visible_style_defined_for_task_cards(self) -> None:
        style_match = re.search(r"<style>(.*)</style>", self.html, re.S)
        self.assertIsNotNone(style_match)
        self.assertIn(".task:focus-visible", style_match.group(1))

    # -- attempts / passed-after-retry -----------------------------------------

    def test_attempt_count_is_read_from_task_data(self) -> None:
        update_fn = self._extract_function("updateTaskRecord")
        self.assertIn("numberOrZero(task.attempts)", update_fn)

    def test_passed_after_retry_is_surfaced_without_renaming_raw_status(self) -> None:
        update_fn = self._extract_function("updateTaskRecord")
        self.assertIn('const passedAfterRetry = status === "pass" && attempts > 1;', update_fn)
        self.assertIn("passed after retry", update_fn)
        # The raw status text passed to the DOM must remain untouched ("pass", not a
        # rewritten label) -- accountability requires attempts to be additive info.
        self.assertIn("setText(record.elements.status, status);", update_fn)

    def test_drawer_meta_also_calls_out_passed_after_retry(self) -> None:
        drawer_fn = self._extract_function("updateDrawerContent")
        self.assertIn('metaParts.push("passed after retry")', drawer_fn)

    # -- unknown vs. zero accounting -------------------------------------------

    def test_unknown_amount_helper_exists(self) -> None:
        self.assertIn("function isUnknownAmount(value)", self.script)
        self.assertIn("return value === null || value === undefined || value === \"\";", self.script)

    def test_task_tokens_render_unknown_label_when_missing(self) -> None:
        self.assertIn('function formatTokens(value, unknown) {\n      if (unknown) return "tok unknown";', self.script)
        update_fn = self._extract_function("updateTaskRecord")
        self.assertIn("const tokensUnknown = isUnknownAmount(task.tokens);", update_fn)
        self.assertIn("formatTokens(tokens, tokensUnknown)", update_fn)

    def test_run_totals_render_unknown_label_when_missing(self) -> None:
        normalize_fn = self._extract_function("normalizePayload")
        self.assertIn("passUnknown: isUnknownAmount(rawPass),", normalize_fn)
        self.assertIn("failUnknown: isUnknownAmount(rawFail),", normalize_fn)
        self.assertIn("tokensUnknown: isUnknownAmount(rawTokens),", normalize_fn)
        update_run_fn = self._extract_function("updateRunRecord")
        self.assertIn("formatCount(run.pass, run.passUnknown)", update_run_fn)
        self.assertIn("formatCount(run.fail, run.failUnknown)", update_run_fn)
        self.assertIn("formatTokens(run.tokens, run.tokensUnknown)", update_run_fn)

    def test_format_count_never_prints_zero_for_unknown(self) -> None:
        self.assertIn(
            'function formatCount(value, unknown) {\n      return unknown ? "unknown" : String(numberOrZero(value));\n    }',
            self.script,
        )

    # -- optional access / blocked_reason metadata -----------------------------

    def test_optional_meta_label_treats_absent_and_present_differently(self) -> None:
        self.assertIn("function optionalMetaLabel(raw) {", self.script)
        self.assertIn("if (raw === undefined) return null;", self.script)
        self.assertIn('return text || "unknown";', self.script)

    def test_access_label_checked_on_both_run_and_task(self) -> None:
        self.assertIn("function accessLabel(source) {", self.script)
        update_fn = self._extract_function("updateTaskRecord")
        self.assertIn("accessLabel(task)", update_fn)
        update_run_fn = self._extract_function("updateRunRecord")
        self.assertIn("accessLabel(run)", update_run_fn)

    def test_access_badge_hidden_when_metadata_absent(self) -> None:
        update_fn = self._extract_function("updateTaskRecord")
        self.assertIn("setHidden(record.elements.access, taskAccess === null);", update_fn)
        update_run_fn = self._extract_function("updateRunRecord")
        self.assertIn("setHidden(record.elements.access, runAccess === null);", update_run_fn)

    def test_blocked_reason_rendered_in_drawer_without_raw_log_lookup(self) -> None:
        self.assertIn("function blockedReasonLabel(task) {", self.script)
        self.assertIn('<div class="drawer-blocked" data-drawer-blocked hidden></div>', self.script)
        drawer_fn = self._extract_function("updateDrawerContent")
        self.assertIn("const blocked = blockedReasonLabel(task);", drawer_fn)
        self.assertIn('setText(refs.blocked, blocked ? `blocked: ${blocked}` : "");', drawer_fn)

    def test_blocked_badge_also_surfaced_on_the_task_card(self) -> None:
        update_fn = self._extract_function("updateTaskRecord")
        self.assertIn("const blocked = blockedReasonLabel(task);", update_fn)
        self.assertIn("setHidden(record.elements.blocked, blocked === null);", update_fn)

    # -- regression guards for untouched behavior ------------------------------

    def test_drawer_content_is_still_escaped(self) -> None:
        drawer_fn = self._extract_function("updateDrawerContent")
        self.assertIn("escapeHtml(spec)", drawer_fn)
        self.assertIn("escapeHtml(check)", drawer_fn)
        self.assertIn("escapeHtml(checkOutput)", drawer_fn)

    def test_worker_log_polling_markers_preserved(self) -> None:
        self.assertIn("WORKER_LOG_POLL_MS", self.script)
        self.assertIn("data-worker-stream", self.script)
        self.assertIn("data-drawer-config-body", self.script)

    # -- helpers ----------------------------------------------------------------

    def _extract_function(self, name: str) -> str:
        match = re.search(rf"function {re.escape(name)}\(", self.script)
        self.assertIsNotNone(match, f"expected a top-level function named {name}")
        start = match.start()
        brace_start = self.script.index("{", match.end())
        depth = 0
        for index in range(brace_start, len(self.script)):
            char = self.script[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return self.script[start : index + 1]
        raise AssertionError(f"could not find closing brace for function {name}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
