"""Helpers for qnxdoctor unit tests."""

from __future__ import annotations

from pathlib import Path

from qnxdoctor.environment import HostSnapshot


def write(root: Path, relative: str, text: str, executable: bool = False) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if executable:
        path.chmod(0o755)
    return path


def snapshot(
    env: dict[str, str],
    home: Path,
    *,
    roots: tuple[Path, ...] = (),
    sdp_root: Path | None = None,
    system: str = "Linux",
    machine: str = "x86_64",
    tools: dict[str, str | None] | None = None,
    make_version: str | None = "GNU Make 4.3",
    qcc_dash_v: str | None = None,
) -> HostSnapshot:
    found = {
        "qcc": None,
        "q++": None,
        "make": "/usr/bin/make",
        "mk": None,
        "mkifs": None,
        "mkqnximage": None,
    }
    if tools:
        found.update(tools)
    return HostSnapshot(
        env=dict(env),
        home=home,
        system=system,
        machine=machine,
        tools=found,
        make_version=make_version,
        qcc_dash_v=qcc_dash_v,
        search_roots=roots,
        sdp_root=sdp_root,
    )


def make_sdp8(root: Path) -> dict[str, str]:
    """Lay down a fake SDP 8.0 tree and return the environment it activates."""

    host = root / "host" / "linux" / "x86_64"
    bindir = host / "usr" / "bin"
    bindir.mkdir(parents=True)
    for name in ("qcc", "q++"):
        tool = bindir / name
        tool.write_text("#!/bin/sh\nprintf '%s\\n' gcc_ntoaarch64le gcc_ntox86_64\n")
        tool.chmod(0o755)
    include = root / "target" / "qnx" / "usr" / "include"
    mk = include / "mk"
    mk.mkdir(parents=True)
    (include / "qconfig.mk").write_text("# qconfig\n")
    (mk / "qtargets.mk").write_text("# qtargets\n")
    (mk / "recurse.mk").write_text("# recurse\n")
    (root / "qnxsdp-env.sh").write_text("# QNX Software Development Platform 8.0\n")
    return {
        "QNX_HOST": str(host),
        "QNX_TARGET": str(include.parent.parent),
        "PATH": f"{bindir}:/usr/bin:/bin",
        "MAKEFLAGS": f"-I{include}",
        "HOME": str(root / "home"),
    }
