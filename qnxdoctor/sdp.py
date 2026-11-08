"""SDP 8.0 facts the doctor checks against.

The numbers here follow the QNX SDP 8.0 Programmer's Guide and the public
SDP 8.0 release notes: Neutrino targets are AArch64 little-endian and x86_64,
32-bit ARM and 32-bit x86 are gone, and ``qnxsdp-env.sh`` publishes QNX_HOST,
QNX_TARGET, PATH, and MAKEFLAGS. There is no ``mk`` compiler. The recursive
makefile system is GNU make plus qconfig.mk, qtargets.mk, and recurse.mk.
"""

from __future__ import annotations

SDP_VERSION = "8.0"

VALID_SPECS = ("gcc_ntoaarch64le", "gcc_ntox86_64")
SPEC_SUFFIXES = ("_cxx", "_gpp", "_cpp")

LEGACY_SPECS = {
    "gcc_ntoarmv7le": "32-bit ARMv7 was removed in SDP 8.0. Use gcc_ntoaarch64le.",
    "gcc_ntoarmle": "Legacy ARM little-endian is not an SDP 8.0 target. Use gcc_ntoaarch64le.",
    "gcc_ntox86": "32-bit x86 was removed in SDP 8.0. Use gcc_ntox86_64.",
    "gcc_ntoaarch64": "The AArch64 spec needs the little-endian suffix: gcc_ntoaarch64le.",
    "gcc_ntoarm64le": "Use gcc_ntoaarch64le.",
    "gcc_ntoarm64": "Use gcc_ntoaarch64le.",
    "gcc_ntoaarch64be": "AArch64 big-endian is not an SDP 8.0 target. Use gcc_ntoaarch64le.",
}

SOURCE_COMMAND = "source ~/qnx800/qnxsdp-env.sh"

SOURCE_HELP = (
    "Source the SDP 8.0 environment in every shell you build from:\n"
    f"  {SOURCE_COMMAND}\n"
    "The script sets QNX_HOST, QNX_TARGET, PATH ($QNX_HOST/usr/bin), and\n"
    "MAKEFLAGS (-I$QNX_TARGET/usr/include) so qcc and qconfig.mk resolve.\n"
    "Project file checks still run when the SDP is not installed."
)

# Warnings that mean "this shell cannot build with SDP 8.0 yet".
# --require-sdp promotes them to errors. Infos are never promoted.
REQUIRE_SDP_IDS = frozenset(
    {
        "env.qnx-host-unset",
        "env.qnx-target-unset",
        "env.qcc-missing",
        "env.qxx-missing",
        "env.qcc-not-on-path",
        "env.qcc-without-host",
        "env.makeflags-missing",
        "env.mk-includes-unverified",
        "env.sdp-not-found",
        "env.sdp-installed-not-sourced",
        "env.path-missing-host-bin",
        "env.make-missing",
        "env.host-unsupported",
        "env.qcc-specs-incomplete",
        "env.qcc-specs-unknown",
    }
)

# Findings that mean the host environment is not ready to compile.
DEGRADED_IDS = REQUIRE_SDP_IDS | frozenset(
    {
        "env.qnx-host-missing",
        "env.qnx-host-is-base",
        "env.qnx-host-sdp7",
        "env.qnx-target-missing",
        "env.qnx-target-not-tree",
        "env.qnx-target-is-base",
        "env.qnx-target-sdp7",
        "env.host-target-mismatch",
        "env.sdp-wrong-version",
        "env.host-os-mismatch",
        "env.mk-includes-missing",
        "env.make-not-gnu",
        "env.qcc-shadowed",
        "env.sdp-root-missing",
        "env.sdp-root-invalid",
        "env.host-include-leak",
        "env.host-lib-leak",
    }
)

OS_NAMES = frozenset({"nto", "linux", "win64"})
BUILD_TYPES = frozenset({"o", "so", "dll", "a", "a.shared"})

# cpu token -> (canonical, problem or None). "be" is handled by the caller.
CPU_INFO = {
    "aarch64": ("aarch64", None),
    "arm64": ("aarch64", None),
    "aarch64le": ("aarch64", None),
    "aarch64be": ("aarch64", "be"),
    "x86_64": ("x86_64", None),
    "amd64": ("x86_64", None),
    "x64": ("x86_64", None),
    "x86": ("x86", "32-bit x86 was removed in SDP 8.0. Use x86_64."),
    "i386": ("i386", "32-bit x86 was removed in SDP 8.0. Use x86_64."),
    "i686": ("i686", "32-bit x86 was removed in SDP 8.0. Use x86_64."),
    "arm": ("arm", "32-bit ARM was removed in SDP 8.0. Use aarch64."),
    "armv7": ("armv7", "32-bit ARMv7 was removed in SDP 8.0. Use aarch64."),
    "armle": ("armle", "32-bit ARM was removed in SDP 8.0. Use aarch64."),
    "armv7le": ("armv7le", "32-bit ARMv7 was removed in SDP 8.0. Use aarch64."),
    "ppc": ("ppc", "PowerPC is not an SDP 8.0 target."),
    "ppcbe": ("ppcbe", "PowerPC is not an SDP 8.0 target."),
    "sh": ("sh", "SuperH is not an SDP 8.0 target."),
    "mips": ("mips", "MIPS is not an SDP 8.0 target."),
    "mipsle": ("mipsle", "MIPS is not an SDP 8.0 target."),
}

# CPUs whose directory token already includes little-endian.
CPU_ENDIAN_IN_NAME = frozenset({"aarch64le"})

LIBC_BUILTINS = ("pthread", "dl", "rt")

PRESET_MACROS = frozenset(
    {
        "NAME",
        "SRCS",
        "LIBS",
        "CC",
        "CXX",
        "CFLAGS",
        "CXXFLAGS",
        "LDFLAGS",
        "LDLIBS",
    }
)

QNX_TEXT_MARKERS = (
    "qcc",
    "q++",
    "QNX",
    "qnx",
    "gcc_nto",
    "qconfig",
    "recurse.mk",
    "QRECURSE",
    "qnxsdp",
)


def describe_spec(spec: str) -> tuple[str, str]:
    """Return ``(kind, detail)``.

    ``kind`` is ``ok``, ``legacy``, ``unknown``, or ``other``.
    ``detail`` is the canonical spec or a short explanation.
    """

    base = spec
    for suffix in SPEC_SUFFIXES:
        if base.endswith(suffix) and len(base) > len(suffix):
            base = base[: -len(suffix)]
            break
    if base in VALID_SPECS:
        return "ok", base
    if base in LEGACY_SPECS:
        return "legacy", LEGACY_SPECS[base]
    if base.startswith("gcc_nt"):
        return (
            "unknown",
            f"{spec} is not an SDP 8.0 qcc spec. Use gcc_ntoaarch64le or gcc_ntox86_64.",
        )
    return "other", spec


def sdp_generation(path: str) -> str | None:
    """Guess 7, 8, or mixed from an install path. Unknown layouts return None."""

    text = str(path).replace("\\", "/")
    parts = [part for part in text.split("/") if part]
    lower_parts = [part.lower() for part in parts]
    joined = "/".join(lower_parts)
    seven = False
    eight = False
    sdpish = any(part in {"sdp", "qnx"} or part.startswith("qnx") for part in lower_parts)
    for part in lower_parts:
        if part.startswith("qnx8") or part in {"qnx800", "qnx80", "qnx8"}:
            eight = True
        elif part.startswith("qnx7") or part.startswith("qnx6") or part in {
            "qnx710",
            "qnx700",
            "qnx660",
            "qnx71",
            "qnx70",
            "qnx7",
        }:
            seven = True
        elif sdpish and part in {"800"}:
            eight = True
        elif sdpish and part in {"710", "700", "660"}:
            seven = True
    if "target/qnx8" in joined:
        eight = True
    if "target/qnx7" in joined:
        seven = True
    if seven and eight:
        return "mixed"
    if eight:
        return "8"
    if seven:
        return "7"
    return None
