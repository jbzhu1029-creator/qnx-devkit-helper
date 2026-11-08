"""Command-line entry for qnxdoctor."""

from __future__ import annotations

import argparse
import os
import sys
import unittest
from pathlib import Path

from qnxdoctor import __version__
from qnxdoctor.diagnose import diagnose
from qnxdoctor.environment import collect_snapshot
from qnxdoctor.present import render_json, render_text

COMMANDS = {"doctor", "demo", "self-test", "version"}
EPILOG = """
examples:
  python3 -m qnxdoctor examples/hello-sdp8
  python3 -m qnxdoctor examples/plain-aarch64
  python3 -m qnxdoctor examples/broken-port
  python3 -m qnxdoctor --format json examples/hello-sdp8
  python3 -m qnxdoctor --require-sdp examples/hello-sdp8
  python3 -m qnxdoctor demo
  python3 -m qnxdoctor self-test

Exit status is 0 when no check is an error, 1 when a check is an error,
and 2 for usage problems. Warnings do not fail the run. Missing SDP is a
warning unless --require-sdp is set, so CI and reviewers can diagnose
project files without installing QNX SDP.
"""


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    else:
        argv = list(argv)
    if not argv:
        normalized = ["doctor"]
    elif argv[0] in {"-h", "--help", "--version"} or argv[0] in COMMANDS:
        normalized = argv
    else:
        normalized = ["doctor", *argv]
    parser = build_parser()
    args = parser.parse_args(normalized)
    if args.command == "version":
        print(f"qnxdoctor {__version__}")
        return 0
    if args.command == "self-test":
        return self_test()
    if args.command == "demo":
        return run_demo(args)
    return run_doctor(args)


def build_parser() -> argparse.ArgumentParser:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--format", choices=("text", "json"), default="text")
    shared.add_argument("--color", choices=("auto", "always", "never"), default="auto")
    shared.add_argument(
        "--require-sdp",
        action="store_true",
        help="treat a missing or inactive SDP 8.0 environment as an error",
    )
    shared.add_argument(
        "--no-discover",
        action="store_true",
        help="do not scan the usual SDP install prefixes; only the environment and --sdp-root are used",
    )
    shared.add_argument(
        "--sdp-root",
        type=Path,
        default=None,
        help="SDP root to inspect (the directory that contains qnxsdp-env.sh)",
    )
    shared.add_argument("--quiet", action="store_true", help="print one summary line (text format only)")

    parser = argparse.ArgumentParser(
        prog="qnxdoctor",
        description="Diagnose a QNX SDP 8.0 host environment and a Makefile project.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EPILOG,
    )
    parser.add_argument("--version", action="version", version=f"qnxdoctor {__version__}")
    sub = parser.add_subparsers(dest="command")

    doctor = sub.add_parser("doctor", parents=[shared], help="diagnose a project directory (the default)")
    doctor.add_argument(
        "path",
        nargs="?",
        default=".",
        help="project directory or Makefile (default: the current directory)",
    )

    sub.add_parser("demo", parents=[shared], help="diagnose the bundled examples")
    sub.add_parser("self-test", help="run the qnxdoctor unit tests")
    sub.add_parser("version", help="print the version")
    return parser


def run_doctor(args: argparse.Namespace) -> int:
    snapshot = collect_snapshot(
        sdp_root=args.sdp_root,
        discover=not args.no_discover,
    )
    report = diagnose(Path(args.path), snapshot, require_sdp=args.require_sdp)
    sys.stdout.write(_render(report, args))
    return 0 if report.status == "pass" else 1


def run_demo(args: argparse.Namespace) -> int:
    examples = find_examples()
    if examples is None:
        print("examples/ was not found. Run qnxdoctor demo from a git clone.", file=sys.stderr)
        return 2
    snapshot = collect_snapshot(
        sdp_root=args.sdp_root,
        discover=not args.no_discover,
    )
    chunks: list[str] = []
    for name, note in (
        ("hello-sdp8", ""),
        ("plain-aarch64", ""),
        ("broken-port", " (expected failures)"),
    ):
        report = diagnose(examples / name, snapshot, require_sdp=args.require_sdp)
        chunks.append(f"======== examples/{name}{note} ========\n{_render(report, args)}")
    sys.stdout.write("\n".join(chunks))
    return 0


def self_test() -> int:
    if os.environ.get("QNXDOCTOR_SELF_TEST") == "1":
        print("self-test is already running", file=sys.stderr)
        return 2
    root = Path(__file__).resolve().parents[1]
    tests = root / "tests"
    if not tests.is_dir():
        print("tests/ was not found. Run self-test from a git clone.", file=sys.stderr)
        return 2
    os.environ["QNXDOCTOR_SELF_TEST"] = "1"
    suite = unittest.defaultTestLoader.discover(str(tests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def find_examples() -> Path | None:
    candidates = [
        Path.cwd() / "examples",
        Path(__file__).resolve().parents[1] / "examples",
    ]
    for candidate in candidates:
        if (candidate / "hello-sdp8" / "common.mk").is_file():
            return candidate
    return None


def _render(report, args: argparse.Namespace) -> str:
    if args.format == "json":
        return render_json(report)
    return render_text(report, color=_use_color(args.color), quiet=args.quiet)


def _use_color(mode: str) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty()
