"""Build the fake SDP 8.0 tree the faceless demo activates.

The tree has the paths ``qnxsdp-env.sh`` would publish: a host ``usr/bin``
with ``qcc`` and ``q++`` stubs, and ``qconfig.mk``, ``qtargets.mk``, and
``recurse.mk`` under the Neutrino sysroot. The stubs answer ``qcc -V`` and
refuse every other invocation. They are not a compiler and not QEMU.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

STUB = """#!/bin/sh
# qnxdoctor demo stub. This is not the QNX compiler.
if [ "${1:-}" = "-V" ]; then
  printf '%s\\n' gcc_ntoaarch64le gcc_ntox86_64
  exit 0
fi
echo "qnxdoctor mock qcc: not a compiler" >&2
exit 1
"""


def build_mock(root: Path) -> dict[str, str]:
    """Create ``root`` and return the variables a sourced SDP shell would export."""

    if root.exists():
        shutil.rmtree(root)
    host = root / "host" / "linux" / "x86_64"
    bindir = host / "usr" / "bin"
    bindir.mkdir(parents=True)
    for name in ("qcc", "q++"):
        tool = bindir / name
        tool.write_text(STUB, encoding="utf-8")
        tool.chmod(0o755)
    include = root / "target" / "qnx" / "usr" / "include"
    mk = include / "mk"
    mk.mkdir(parents=True)
    (include / "qconfig.mk").write_text("# qconfig\n", encoding="utf-8")
    (mk / "qtargets.mk").write_text("# qtargets\n", encoding="utf-8")
    (mk / "recurse.mk").write_text("# recurse\n", encoding="utf-8")
    (root / "qnxsdp-env.sh").write_text(
        "# QNX Software Development Platform 8.0\n"
        "# Demo stub. Not a real SDP install.\n",
        encoding="utf-8",
    )
    target = include.parent.parent
    return {
        "QNX_HOST": str(host),
        "QNX_TARGET": str(target),
        "PATH": f"{bindir}:/usr/bin:/bin",
        "MAKEFLAGS": f"-I{include}",
    }


def export_lines(root: Path) -> str:
    env = build_mock(root)
    lines = []
    for key in ("QNX_HOST", "QNX_TARGET", "PATH", "MAKEFLAGS"):
        lines.append(f"export {key}={_quote(env[key])}")
    return "\n".join(lines) + "\n"


def _quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] != "--export":
        print("usage: mock_env.py --export ROOT", file=sys.stderr)
        return 2
    sys.stdout.write(export_lines(Path(argv[2])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
