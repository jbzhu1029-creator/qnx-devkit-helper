"""The faceless demo runs without a QNX SDP, and the narration matches it."""

from __future__ import annotations

import importlib.util
import platform
import re
import subprocess
import sys
import unittest
from pathlib import Path

from qnxdoctor import __version__

REPO = Path(__file__).resolve().parents[1]


def load_demo():
    path = REPO / "demo" / "run_demo.py"
    spec = importlib.util.spec_from_file_location("qnxdoctor_run_demo", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def spoken_sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = line[3:].strip()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


class DemoScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.demo = load_demo()

    def test_narration_timestamps_match_the_session(self) -> None:
        text = (REPO / "demo" / "narration.md").read_text(encoding="utf-8")
        sections = spoken_sections(text)
        stamps = [cue.stamp for cue in self.demo.CUES]
        self.assertEqual(list(sections), stamps)
        self.assertIn(__version__, text)
        self.assertLessEqual(self.demo.END, 150)
        self.assertEqual(self.demo.CUES[-1].at < self.demo.END, True)
        boundaries = [cue.at for cue in self.demo.CUES] + [self.demo.END]
        total = 0
        for index, cue in enumerate(self.demo.CUES):
            words = sections[cue.stamp].split()
            total += len(words)
            gap = boundaries[index + 1] - cue.at
            # 130 words per minute leaves a little air before the next cue.
            self.assertLessEqual(len(words) / 130 * 60, gap + 0.05, cue.stamp)
        self.assertLessEqual(total, 375)
        self.assertGreater(total, 200)

    def test_tape_plays_the_same_session(self) -> None:
        tape = (REPO / "demo" / "qnxdoctor.tape").read_text(encoding="utf-8")
        self.assertIn("python3 demo/run_demo.py --play", tape)
        sleeps = [int(match) for match in re.findall(r"^Sleep (\d+)s$", tape, re.MULTILINE)]
        self.assertEqual(len(sleeps), 1)
        self.assertGreaterEqual(sleeps[0], self.demo.END + 3)

    def test_check_runs_every_command(self) -> None:
        machine = platform.machine().lower()
        if platform.system() != "Linux" or machine not in {"x86_64", "amd64"}:
            self.skipTest("demo transcript is pinned to x86_64 Linux")
        completed = subprocess.run(
            [sys.executable, "demo/run_demo.py", "--check"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("qnxdoctor faceless demo", completed.stdout)
        self.assertIn("$ source demo/mock-env.sh", completed.stdout)
        self.assertIn("mode    : ready", completed.stdout)
        self.assertIn("examples/broken-port", completed.stdout)
        self.assertIn('"mode": "degraded"', completed.stdout)

    def test_mock_stub_lists_specs_and_refuses_to_compile(self) -> None:
        completed = subprocess.run(
            [
                "bash",
                "--noprofile",
                "--norc",
                "-c",
                "source demo/mock-env.sh\n"
                'qcc -V >"$1"\n'
                'qcc -c hello.c >"$2" 2>&1\n'
                "echo compile:$?\n",
                "bash",
                "/tmp/qnxdoctor-qcc-v",
                "/tmp/qnxdoctor-qcc-c",
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        specs = Path("/tmp/qnxdoctor-qcc-v").read_text(encoding="utf-8")
        self.assertIn("gcc_ntoaarch64le", specs)
        self.assertIn("gcc_ntox86_64", specs)
        self.assertIn("compile:1", completed.stdout)
        refusal = Path("/tmp/qnxdoctor-qcc-c").read_text(encoding="utf-8")
        self.assertIn("not a compiler", refusal)

    def test_sourcing_is_required(self) -> None:
        completed = subprocess.run(
            ["bash", "demo/mock-env.sh"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("Source this file", completed.stderr)


if __name__ == "__main__":
    unittest.main()
