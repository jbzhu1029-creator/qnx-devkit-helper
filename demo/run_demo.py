"""Scripted qnxdoctor session for the hackathon demo.

``--check`` runs every command and checks the output. It needs no QNX SDP
and does not sleep. ``--play`` runs the same commands on the clock in
``demo/narration.md`` (about two and a half minutes).

The degraded commands scrub QNX variables and pass ``--no-discover``, so a
machine that happens to have an SDP install still shows the degraded
transcript. The ready command uses ``demo/mock-env.sh``.

Expected counts are for x86_64 Linux with GNU make on ``/usr/bin`` or
``/bin``, which is the SDP 8.0 host this demo records.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from qnxdoctor import __version__
END = 149

BANNER = (
    "qnxdoctor faceless demo\n"
    "No QNX SDP is installed for this session. Examples are the ones in this repo.\n"
    "\n"
)

SCRUB = {
    "MAKEFLAGS",
    "CPATH",
    "C_INCLUDE_PATH",
    "CPLUS_INCLUDE_PATH",
    "LIBRARY_PATH",
}


@dataclass(frozen=True)
class Cue:
    at: int
    kind: str
    args: tuple[str, ...] = ()
    env: str = "clean"
    expect: int = 0
    needles: tuple[str, ...] = ()

    @property
    def stamp(self) -> str:
        return f"{self.at // 60}:{self.at % 60:02d}"


# Times are the narration headings in demo/narration.md.
CUES = (
    Cue(0, "banner"),
    Cue(14, "command", ("version",), needles=(f"qnxdoctor {__version__}",)),
    Cue(
        22,
        "command",
        ("demo", "--no-discover", "--color", "never", "--quiet"),
        needles=(
            "======== examples/hello-sdp8 ========",
            "======== examples/plain-aarch64 ========",
            "======== examples/broken-port (expected failures) ========",
            "degraded  pass",
            "degraded  fail",
        ),
    ),
    Cue(
        46,
        "command",
        ("--no-discover", "--color", "never", "examples/broken-port"),
        expect=1,
        needles=(
            "\nErrors\n",
            "variant.cpu-unsupported",
            "variant.big-endian",
            "project.host-compiler",
            "project.march-native",
            "project.legacy-sdp-path",
            "mk.qtargets-missing",
            "source.linux-header",
            "Summary: fail, mode degraded",
        ),
    ),
    Cue(78, "mock"),
    Cue(
        90,
        "command",
        ("--no-discover", "--color", "never", "examples/hello-sdp8"),
        env="mock",
        needles=(
            "mode    : ready",
            "status  : pass",
            "env.qcc-specs",
            "gcc_ntoaarch64le",
            "gcc_ntox86_64",
            "env.mk-includes",
        ),
    ),
    Cue(
        110,
        "command",
        ("--no-discover", "--color", "never", "--require-sdp", "--quiet", "examples/hello-sdp8"),
        expect=1,
        needles=("degraded  fail", "7 errors"),
    ),
    Cue(
        124,
        "command",
        ("--no-discover", "--color", "never", "--format", "json", "examples/hello-sdp8"),
        needles=('"status": "pass"', '"mode": "degraded"', '"style": "qnx-mk"'),
    ),
    Cue(136, "hold"),
)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args in (["-h"], ["--help"]):
        print("usage: python3 demo/run_demo.py --play | --check")
        return 0
    if args == ["--play"]:
        return run_session(play=True)
    if args == ["--check"]:
        return run_session(play=False)
    print("usage: python3 demo/run_demo.py --play | --check", file=sys.stderr)
    return 2


def run_session(play: bool) -> int:
    if not _supported_host():
        return 2
    clock = _Clock(play)
    clean = _clean_env()
    mock: dict[str, str] | None = None
    clock.start()
    for cue in CUES:
        clock.wait(cue.at)
        if cue.kind == "banner":
            _write(BANNER)
            continue
        if cue.kind == "hold":
            continue
        if cue.kind == "mock":
            mock = _activate_mock(clean)
            if mock is None:
                return 1
            continue
        env = clean if cue.env == "clean" else mock
        if env is None:
            print("mock SDP was not activated", file=sys.stderr)
            return 1
        result = _invoke(cue.args, env)
        _show_command(cue.args, result)
        if result.returncode != cue.expect:
            print(
                f"{cue.stamp}: exit {result.returncode}, expected {cue.expect}",
                file=sys.stderr,
            )
            return 1
        for needle in cue.needles:
            if needle not in result.stdout:
                print(f"{cue.stamp}: output missing {needle!r}", file=sys.stderr)
                return 1
    clock.wait(END)
    return 0


def _supported_host() -> bool:
    machine = platform.machine().lower()
    if platform.system() == "Linux" and machine in {"x86_64", "amd64"}:
        return True
    print(
        "This demo's transcript is for x86_64 Linux, the SDP 8.0 host used in CI.",
        file=sys.stderr,
    )
    print(f"This machine is {platform.system()} {platform.machine()}.", file=sys.stderr)
    return False


def _clean_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("QNX") or key in SCRUB:
            env.pop(key, None)
    env["PATH"] = "/usr/bin:/bin"
    env["NO_COLOR"] = "1"
    return env


def _activate_mock(clean: dict[str, str]) -> dict[str, str] | None:
    script = REPO / "demo" / "mock-env.sh"
    proc = subprocess.run(
        [
            "bash",
            "--noprofile",
            "--norc",
            "-c",
            'source "$1" && printf "%s\\0%s\\0%s\\0%s\\0" "$QNX_HOST" "$QNX_TARGET" "$PATH" "$MAKEFLAGS"',
            "bash",
            str(script),
        ],
        cwd=REPO,
        env=clean,
        capture_output=True,
        text=True,
        check=False,
    )
    _write("$ source demo/mock-env.sh\n")
    if proc.returncode != 0 or proc.stdout.count("\0") < 4:
        sys.stdout.write(proc.stdout)
        sys.stdout.write(proc.stderr)
        print("source demo/mock-env.sh failed", file=sys.stderr)
        return None
    host, target, path, makeflags, _rest = proc.stdout.split("\0", 4)
    env = dict(clean)
    env["QNX_HOST"] = host
    env["QNX_TARGET"] = target
    env["PATH"] = path
    env["MAKEFLAGS"] = makeflags
    listed = subprocess.run(
        [str(Path(host) / "usr" / "bin" / "qcc"), "-V"],
        capture_output=True,
        text=True,
        check=False,
    )
    shown = (
        f"QNX_HOST={host}\n"
        f"QNX_TARGET={target}\n"
        f"MAKEFLAGS={makeflags}\n"
        "qcc -V\n"
        f"{listed.stdout}"
    )
    if listed.returncode != 0 or "gcc_ntoaarch64le" not in listed.stdout or "gcc_ntox86_64" not in listed.stdout:
        _write(shown)
        if listed.stderr:
            _write(listed.stderr)
        print("mock qcc -V did not list the SDP 8.0 specs", file=sys.stderr)
        return None
    if not shown.endswith("\n"):
        shown += "\n"
    _write(shown + "exit 0\n\n")
    return env


def _invoke(args: tuple[str, ...], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "qnxdoctor", *args],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _show_command(args: tuple[str, ...], result: subprocess.CompletedProcess[str]) -> None:
    _write("$ python3 -m qnxdoctor " + " ".join(args) + "\n")
    if result.stdout:
        _write(result.stdout)
    if result.stderr:
        _write(result.stderr if result.stderr.endswith("\n") else result.stderr + "\n")
    if result.stdout and not result.stdout.endswith("\n"):
        _write("\n")
    _write(f"exit {result.returncode}\n\n")


def _write(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


class _Clock:
    def __init__(self, play: bool) -> None:
        self.play = play
        self.started = 0.0

    def start(self) -> None:
        self.started = time.monotonic()

    def wait(self, second: float) -> None:
        if not self.play:
            return
        delay = second - (time.monotonic() - self.started)
        if delay > 0:
            time.sleep(delay)


if __name__ == "__main__":
    raise SystemExit(main())
