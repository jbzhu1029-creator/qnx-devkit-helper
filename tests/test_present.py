"""Text report layout. The error recap is what stays on screen after a long run."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from test_cli import run_cli

REPO = Path(__file__).resolve().parents[1]


class PresentTests(unittest.TestCase):
    def test_clean_report_has_no_error_recap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            completed = run_cli(
                ["--no-discover", "--color", "never", "examples/hello-sdp8"],
                home=Path(tmp),
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        text = completed.stdout
        self.assertNotIn("\nErrors\n", text)
        self.assertIn("\nSummary: pass, mode degraded, 0 errors, ", text)
        self.assertLess(text.index("\nPassed\n"), text.index("\nSummary:"))

    def test_failures_are_repeated_after_passed_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            completed = run_cli(
                ["--no-discover", "--color", "never", "examples/broken-port"],
                home=Path(tmp),
            )
        self.assertEqual(completed.returncode, 1, completed.stdout)
        text = completed.stdout
        passed_at = text.index("\nPassed\n")
        errors_at = text.index("\nErrors\n")
        summary_at = text.index("\nSummary:")
        self.assertLess(passed_at, errors_at)
        self.assertLess(errors_at, summary_at)
        recap = text[errors_at:summary_at]
        for check_id in (
            "mk.qtargets-missing",
            "project.host-compiler",
            "project.legacy-sdp-path",
            "project.march-native",
            "source.linux-header",
            "variant.big-endian",
            "variant.cpu-unsupported",
        ):
            self.assertIn(check_id, recap)
        # The long fix text stays in the Project section only.
        help_line = "Add `include $(MKFILES_ROOT)/qtargets.mk`"
        self.assertEqual(text.count(help_line), 1)
        self.assertNotIn(help_line, recap)
        self.assertIn("Summary: fail, mode degraded, 7 errors, ", text)

    def test_quiet_stays_one_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            completed = run_cli(
                ["--no-discover", "--color", "never", "--quiet", "examples/broken-port"],
                home=Path(tmp),
            )
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout.count("\n"), 1)
        self.assertNotIn("Errors", completed.stdout)
        self.assertIn(" fail ", completed.stdout)


if __name__ == "__main__":
    unittest.main()
