"""CLI exit codes. The process environment is scrubbed so a real SDP is not required."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from qnxdoctor import __version__
from qnxdoctor.cli import main
from support import make_sdp8

REPO = Path(__file__).resolve().parents[1]


def run_cli(args: list[str], env: dict[str, str] | None = None, home: Path | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    for key in list(merged):
        if key.startswith("QNX") or key in {
            "MAKEFLAGS",
            "CPATH",
            "C_INCLUDE_PATH",
            "CPLUS_INCLUDE_PATH",
            "LIBRARY_PATH",
        }:
            merged.pop(key, None)
    merged["PATH"] = "/usr/bin:/bin"
    merged["NO_COLOR"] = "1"
    if home is not None:
        merged["HOME"] = str(home)
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, "-m", "qnxdoctor", *args],
        cwd=REPO,
        env=merged,
        capture_output=True,
        text=True,
        check=False,
    )


class CliTests(unittest.TestCase):
    def test_version_matches_package_and_pyproject(self) -> None:
        text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(f'version = "{__version__}"', text)
        completed = run_cli(["version"])
        self.assertEqual(completed.returncode, 0)
        self.assertIn(__version__, completed.stdout)

    def test_hello_passes_in_degraded_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            completed = run_cli(
                ["--no-discover", "--format", "json", "examples/hello-sdp8"],
                home=Path(tmp),
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["mode"], "degraded")
        self.assertEqual(payload["style"], "qnx-mk")
        finding_ids = {item["id"] for item in payload["findings"]}
        self.assertIn("env.qcc-missing", finding_ids)
        self.assertNotIn("project.host-compiler", finding_ids)

    def test_require_sdp_promotes_missing_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            completed = run_cli(
                ["--no-discover", "--require-sdp", "--format", "json", "examples/hello-sdp8"],
                home=Path(tmp),
            )
        self.assertEqual(completed.returncode, 1, completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "fail")
        promoted = [item for item in payload["findings"] if item.get("promoted") and item["id"] == "env.qcc-missing"]
        self.assertEqual(len(promoted), 1)
        self.assertEqual(promoted[0]["severity"], "error")

    def test_broken_example_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            completed = run_cli(
                ["--no-discover", "--color", "never", "examples/broken-port"],
                home=Path(tmp),
            )
        self.assertEqual(completed.returncode, 1, completed.stdout)
        self.assertIn("project.host-compiler", completed.stdout)
        self.assertIn("variant.cpu-unsupported", completed.stdout)

    def test_repo_root_points_at_the_examples(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            completed = run_cli(["--no-discover", "--color", "never", "."], home=Path(tmp))
        self.assertEqual(completed.returncode, 1)
        self.assertIn("project.missing", completed.stdout)
        self.assertIn("examples/hello-sdp8", completed.stdout)

    def test_demo_runs_all_three_examples(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            completed = run_cli(["demo", "--no-discover", "--color", "never"], home=Path(tmp))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("examples/hello-sdp8", completed.stdout)
        self.assertIn("examples/plain-aarch64", completed.stdout)
        self.assertIn("examples/broken-port", completed.stdout)

    def test_fake_sdp_on_the_command_line_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "qnx800"
            env = make_sdp8(root)
            completed = run_cli(
                ["--no-discover", "--sdp-root", str(root), "--format", "json", "examples/hello-sdp8"],
                env=env,
                home=Path(env["HOME"]),
            )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["mode"], "ready")
        self.assertEqual(payload["status"], "pass")
        passed = {item["id"] for item in payload["passed"]}
        self.assertIn("env.qcc-specs", passed)

    def test_main_version_returns_zero(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            code = main(["version"])
        self.assertEqual(code, 0)
        self.assertIn(__version__, captured.getvalue())


if __name__ == "__main__":
    unittest.main()
