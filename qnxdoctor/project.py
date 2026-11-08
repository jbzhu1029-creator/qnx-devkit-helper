"""Makefile and source checks that do not need a QNX SDP install."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from qnxdoctor.makeparse import ParsedFile, include_kinds, parse_makefile
from qnxdoctor.notes import Note
from qnxdoctor.sdp import (
    BUILD_TYPES,
    CPU_ENDIAN_IN_NAME,
    CPU_INFO,
    LIBC_BUILTINS,
    OS_NAMES,
    PRESET_MACROS,
    QNX_TEXT_MARKERS,
    describe_spec,
)

MAKEFILE_NAMES = ("Makefile", "makefile", "GNUmakefile")
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "stage",
}
SOURCE_EXTS = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}
CXX_EXTS = {".cc", ".cpp", ".cxx"}
SPEC_RE = re.compile(r"-V\s*([A-Za-z0-9_+.]+)")
LEGACY_RE = re.compile(
    r"qnx(?:660|700|710)\b|target/qnx7\b|sdp[/\\]710\b|sdp[/\\]700\b",
    re.IGNORECASE,
)
MARCH_RE = re.compile(r"-march=native\b|-mtune=native\b")
HOST_INC_RE = re.compile(r"(?:^|\s)-I\s*/usr/include\b")
HOST_LIB_RE = re.compile(r"(?:^|\s)-L\s*/usr/lib(?:64)?\b")
SOCKET_RE = re.compile(
    r"\b(?:socket|bind|listen|accept|connect|sendto|recvfrom|getaddrinfo|inet_pton|inet_ntop)\s*\("
)
INCLUDE_RE = re.compile(r'^\s*#\s*include\s*[<"]([^>"]+)[>"]')
INVOKE_RE = re.compile(r"\b(?:make|qcc|q\+\+|mkifs|mkqnximage)\b")

CLASSIC_CPUS = {
    "aarch64": "aarch64",
    "x86_64": "x86_64",
    "arm": "arm",
    "armv7": "armv7",
    "x86": "x86",
}

BAD_HEADERS = {
    "sys/epoll.h": (
        "source.epoll",
        "warning",
        "QNX has no epoll. SDP 8.0 networking is the io-sock stack; use poll, select, or kqueue/kevent.",
    ),
    "sys/inotify.h": (
        "source.inotify",
        "warning",
        "inotify is Linux-specific. QNX does not provide it.",
    ),
    "sys/eventfd.h": (
        "source.eventfd",
        "warning",
        "eventfd is Linux-specific and is not in the QNX sysroot.",
    ),
    "windows.h": (
        "source.windows-header",
        "error",
        "windows.h is a Windows header and is not part of the Neutrino sysroot.",
    ),
    "winsock2.h": (
        "source.windows-header",
        "error",
        "WinSock is not available on QNX. Use the POSIX socket API and link socket.",
    ),
}


@dataclass
class Variant:
    name: str
    path: Path
    os_name: str
    cpu: str
    tokens: tuple[str, ...]
    classic: bool = False


@dataclass
class ProjectResult:
    root: Path
    style: str
    notes: list[Note] = field(default_factory=list)


def diagnose_project(path: Path) -> ProjectResult:
    located = locate_root(path)
    if not located.exists():
        return ProjectResult(
            root=located,
            style="missing",
            notes=[
                _note(
                    "project.missing",
                    "error",
                    f"No such path: {path}",
                    missing_project_help(path),
                )
            ],
        )

    root = located
    files = discover_makefiles(root)
    cmake = root / "CMakeLists.txt"
    has_cmake = cmake.is_file()
    if not files and not has_cmake and not (root / "common.mk").is_file():
        return ProjectResult(
            root=root,
            style="missing",
            notes=[
                _note(
                    "project.missing",
                    "error",
                    "No Makefile, common.mk, or CMakeLists.txt in this directory.",
                    missing_project_help(root),
                )
            ],
        )

    parsed = load_parsed(root, files)
    variants = iter_variants(root)
    style = detect_style(parsed, variants, has_cmake)
    notes: list[Note] = []

    if style == "plain" and not _looks_like_qnx(parsed, variants):
        notes.append(
            _note(
                "project.not-qnx",
                "error",
                "This Makefile does not target QNX.",
                "For a plain SDP 8.0 Makefile set:\n"
                "  CC = qcc\n"
                "  TARGET_ARCH = -Vgcc_ntoaarch64le\n"
                "Or use the recursive mk layout: common.mk (qconfig.mk and qtargets.mk), "
                "a root Makefile that includes recurse.mk, and a variant directory such as nto-aarch64-o-le.",
                path=_primary_makefile(parsed),
            )
        )
        _check_recipe_indents(parsed, root, notes)
        return ProjectResult(root=root, style=style, notes=notes)

    if style == "cmake" and not _cmake_looks_like_qnx(cmake):
        notes.append(
            _note(
                "project.not-qnx",
                "error",
                "CMakeLists.txt does not mention qcc or QNX.",
                "Point CMAKE_C_COMPILER at qcc and pass a spec such as gcc_ntoaarch64le, "
                "or add a QNX toolchain file. qnxdoctor's full checks are for Makefiles.",
                path="CMakeLists.txt",
            )
        )
        return ProjectResult(root=root, style=style, notes=notes)

    if style == "qnx-mk":
        notes.append(
            _note(
                "mk.layout",
                "ok",
                "Recursive QNX mk layout detected (common.mk, recurse.mk, or variant directories).",
            )
        )
    elif style == "plain":
        notes.append(
            _note(
                "plain.layout",
                "ok",
                "Plain Makefile that mentions the QNX toolchain.",
            )
        )
    else:
        notes.append(_note("cmake.layout", "ok", "CMakeLists.txt mentions QNX. Makefile checks are skipped."))

    _check_includes(parsed, style, notes, root)
    _check_list(parsed, variants, style, notes, root)
    _check_compilers(parsed, style, root, notes)
    _check_specs(parsed, style, notes, root)
    _check_preset_order(parsed, root, notes)
    _check_variants(variants, parsed, root, notes)
    _check_text_pitfalls(parsed, root, notes)
    _check_recipe_indents(parsed, root, notes)
    _check_destdir(parsed, notes, root)
    sources = walk_sources(root)
    _check_listed_sources(parsed, sources, root, notes)
    _check_sources(sources, parsed, root, notes)
    _check_scripts(root, notes)
    if has_cmake and style != "cmake":
        _check_cmake_advisory(cmake, root, notes)
    if style == "cmake":
        _check_cmake_body(cmake, root, notes)
    return ProjectResult(root=root, style=style, notes=notes)


def locate_root(path: Path) -> Path:
    path = path.expanduser()
    if not path.exists():
        return path
    path = path.resolve()
    if path.is_file():
        path = path.parent
    for _ in range(4):
        parent = path.parent
        if parent == path:
            break
        if _variant_dirname(path.name) is not None and (parent / "common.mk").is_file():
            path = parent
            continue
        break
    return path


def missing_project_help(path: Path) -> str:
    bases = []
    if path.exists() and path.is_dir():
        bases.append(path)
    bases.append(path.parent if path.exists() else path)
    bases.append(Path.cwd())
    bases.append(Path(__file__).resolve().parents[1])
    seen: set[Path] = set()
    for base in bases:
        try:
            key = base.resolve()
        except OSError:
            key = base
        if key in seen:
            continue
        seen.add(key)
        if (base / "examples" / "hello-sdp8" / "common.mk").is_file():
            try:
                rel = Path(os.path.relpath(base / "examples", Path.cwd())).as_posix()
            except ValueError:
                rel = str(base / "examples")
            return (
                "Point qnxdoctor at a QNX project:\n"
                f"  python3 -m qnxdoctor {rel}/hello-sdp8\n"
                f"  python3 -m qnxdoctor {rel}/plain-aarch64\n"
                f"  python3 -m qnxdoctor {rel}/broken-port"
            )
    return "Pass the directory that contains the project's Makefile or common.mk."


def discover_makefiles(root: Path) -> list[Path]:
    found: list[Path] = []
    if not root.is_dir():
        return found
    for name in (*MAKEFILE_NAMES, "common.mk"):
        candidate = root / name
        if candidate.is_file():
            found.append(candidate)
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if _variant_dirname(child.name) is None and child.name not in CLASSIC_CPUS:
            continue
        for name in MAKEFILE_NAMES:
            candidate = child / name
            if candidate.is_file():
                found.append(candidate)
    return found


def load_parsed(root: Path, files: list[Path]) -> list[ParsedFile]:
    ordered: list[Path] = []
    parsed_by: dict[Path, ParsedFile] = {}
    queue = list(files)
    while queue and len(ordered) < 40:
        current = queue.pop(0)
        try:
            key = current.resolve()
        except OSError:
            key = current
        if key in parsed_by:
            continue
        if not current.is_file():
            continue
        parsed = parse_makefile(current)
        parsed_by[key] = parsed
        ordered.append(key)
        for statement in parsed.statements:
            if statement.kind != "include" or "$" in statement.text:
                continue
            for token in statement.text.split():
                candidate = (current.parent / token).resolve()
                if candidate in parsed_by or not candidate.is_file():
                    continue
                if not _within(root, candidate):
                    continue
                queue.append(candidate)
    return [parsed_by[path] for path in ordered]


def iter_variants(root: Path) -> list[Variant]:
    variants: list[Variant] = []
    if not root.is_dir():
        return variants
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if not child.is_dir() or child.name.startswith("."):
            continue
        parsed = _variant_dirname(child.name)
        if parsed is not None:
            os_name, cpu, tokens = parsed
            variants.append(Variant(child.name, child, os_name, cpu, tokens, classic=False))
            continue
        if child.name in CLASSIC_CPUS and _has_makefile(child):
            variants.append(
                Variant(
                    child.name,
                    child,
                    "nto",
                    CLASSIC_CPUS[child.name],
                    (),
                    classic=True,
                )
            )
    return variants


def detect_style(parsed: list[ParsedFile], variants: list[Variant], has_cmake: bool) -> str:
    for item in parsed:
        if item.path.name == "common.mk":
            return "qnx-mk"
        for statement in item.statements:
            kinds = include_kinds(statement)
            if kinds & {"qconfig.mk", "qtargets.mk", "recurse.mk"}:
                return "qnx-mk"
            if statement.kind == "assign" and statement.name == "LIST":
                tokens = set(statement.value.split())
                if tokens & {"OS", "CPU", "VARIANT"}:
                    return "qnx-mk"
    if variants:
        return "qnx-mk"
    if parsed:
        return "plain"
    if has_cmake:
        return "cmake"
    return "missing"


def _looks_like_qnx(parsed: list[ParsedFile], variants: list[Variant]) -> bool:
    if variants:
        return True
    for item in parsed:
        for statement in item.statements:
            blob = f"{statement.text}\n{statement.value}"
            if any(marker in blob for marker in QNX_TEXT_MARKERS):
                return True
    return False


def _cmake_looks_like_qnx(cmake: Path) -> bool:
    if not cmake.is_file():
        return False
    text = _read_text(cmake)
    return any(marker in text for marker in QNX_TEXT_MARKERS)


def _check_includes(parsed: list[ParsedFile], style: str, notes: list[Note], root: Path) -> None:
    if style != "qnx-mk":
        return
    kinds: set[str] = set()
    for item in parsed:
        for statement in item.statements:
            kinds |= include_kinds(statement)
    if "qconfig.mk" in kinds:
        notes.append(_note("mk.qconfig-included", "ok", "The project includes qconfig.mk."))
    else:
        notes.append(
            _note(
                "mk.qconfig-missing",
                "error",
                "common.mk never includes qconfig.mk.",
                "The SDP template starts with:\n"
                "  ifndef QCONFIG\n"
                "  QCONFIG=qconfig.mk\n"
                "  endif\n"
                "  include $(QCONFIG)\n"
                "qconfig.mk is found via MAKEFLAGS after sourcing qnxsdp-env.sh. It selects qcc and the install roots.",
                path=_rel_named(parsed, root, "common.mk"),
            )
        )
    if "qtargets.mk" in kinds:
        notes.append(_note("mk.qtargets-included", "ok", "The project includes qtargets.mk."))
    else:
        notes.append(
            _note(
                "mk.qtargets-missing",
                "error",
                "The mk project never includes qtargets.mk.",
                "Add `include $(MKFILES_ROOT)/qtargets.mk` after NAME, SRCS, and LIBS. "
                "That file supplies the all, clean, and install rules. Without it, make in a variant directory has nothing to build.",
                path=_rel_named(parsed, root, "common.mk"),
            )
        )
    if "recurse.mk" in kinds:
        notes.append(
            _note(
                "mk.recurse-included",
                "ok",
                "The root Makefile includes recurse.mk, so variant directories are visited.",
            )
        )
    else:
        notes.append(
            _note(
                "mk.recurse-missing",
                "error",
                "The root Makefile does not include recurse.mk.",
                "Variant directories are not built by a top-level `make` unless the root Makefile includes recurse.mk. "
                "The SDP template sets QRECURSE=recurse.mk and then `include $(QRDIR)$(QRECURSE)`.",
                path=_primary_makefile(parsed),
            )
        )


def _check_list(
    parsed: list[ParsedFile],
    variants: list[Variant],
    style: str,
    notes: list[Note],
    root: Path,
) -> None:
    if style != "qnx-mk" or not variants:
        return
    flat = [variant for variant in variants if not variant.classic]
    if not flat:
        return
    value = _merged_variables(parsed).get("LIST")
    if value is None:
        notes.append(
            _note(
                "mk.list-incomplete",
                "warning",
                "The root Makefile does not set LIST=OS CPU VARIANT.",
                "Flat directories such as nto-aarch64-o-le are decoded with `LIST=OS CPU VARIANT`. "
                "Without it the mk system will not treat the directory name as OS, CPU, and variant.",
                path=_primary_makefile(parsed),
            )
        )
        return
    tokens = set(value.split())
    missing = [name for name in ("OS", "CPU", "VARIANT") if name not in tokens]
    if missing:
        joined = " and ".join(missing) if len(missing) < 3 else ", ".join(missing[:-1]) + ", and " + missing[-1]
        notes.append(
            _note(
                "mk.list-incomplete",
                "warning",
                f"LIST is `{value}` and is missing {joined}.",
                "For directories named OS-CPU-VARIANT the root Makefile needs `LIST=OS CPU VARIANT`.",
                path=_assign_location(parsed, root, "LIST"),
                line=_assign_line(parsed, "LIST"),
            )
        )
    else:
        notes.append(_note("mk.list", "ok", "LIST includes OS, CPU, and VARIANT."))


def _check_compilers(parsed: list[ParsedFile], style: str, root: Path, notes: list[Note]) -> None:
    cc_assigns = []
    cxx_assigns = []
    host_hit = False
    for item in parsed:
        rel = _rel(root, item.path)
        for statement in item.statements:
            if statement.kind != "assign" or statement.name not in {"CC", "CXX"}:
                continue
            bucket = cc_assigns if statement.name == "CC" else cxx_assigns
            bucket.append(statement)
            kind = compiler_kind(statement.value)
            if kind == "host":
                host_hit = True
                notes.append(
                    _note(
                        "project.host-compiler",
                        "error",
                        f"{statement.name} is set to the host compiler ({statement.value}).",
                        _host_compiler_help(style, statement.name),
                        path=rel,
                        line=statement.line,
                    )
                )
            elif kind == "empty":
                notes.append(
                    _note(
                        "project.host-compiler",
                        "error",
                        f"{statement.name} is set to an empty value.",
                        _host_compiler_help(style, statement.name),
                        path=rel,
                        line=statement.line,
                    )
                )
            elif kind == "other":
                notes.append(
                    _note(
                        "project.unknown-compiler",
                        "warning",
                        f"{statement.name} is `{statement.value}`, not qcc or q++.",
                        "SDP 8.0 builds should use the qcc driver. A wrapper is fine if it ends up calling qcc.",
                        path=rel,
                        line=statement.line,
                    )
                )
    if style == "plain":
        if not cc_assigns and not host_hit:
            notes.append(
                _note(
                    "project.host-compiler",
                    "error",
                    "CC is unset, so GNU make will compile with the host cc.",
                    _host_compiler_help("plain", "CC"),
                    path=_primary_makefile(parsed),
                )
            )
        elif cc_assigns and not host_hit and all(compiler_kind(item.value) == "qcc" for item in cc_assigns):
            notes.append(_note("project.compiler", "ok", "CC is qcc."))
        cxx_sources = any(path.suffix.lower() in CXX_EXTS for path in walk_sources(root))
        if cxx_sources and not cxx_assigns:
            notes.append(
                _note(
                    "project.host-compiler",
                    "error",
                    "CXX is unset and the project has C++ sources, so GNU make will use the host c++.",
                    _host_compiler_help("plain", "CXX"),
                )
            )
        return
    if style == "qnx-mk" and not cc_assigns and not cxx_assigns:
        notes.append(
            _note(
                "mk.compiler-unpinned",
                "ok",
                "CC is not overridden. qconfig.mk will supply qcc.",
            )
        )
    elif style == "qnx-mk" and not host_hit and cc_assigns:
        notes.append(
            _note(
                "mk.compiler-pinned",
                "info",
                "CC is set explicitly. qconfig.mk already selects qcc; a hard-coded driver skips site overrides.",
            )
        )


def _check_specs(parsed: list[ParsedFile], style: str, notes: list[Note], root: Path) -> None:
    found_ok = False
    saw_nto_spec = False
    host_error = any(note.check_id == "project.host-compiler" and note.severity == "error" for note in notes)
    for item in parsed:
        rel = _rel(root, item.path)
        for statement in item.statements:
            for spec in SPEC_RE.findall(statement.text):
                kind, detail = describe_spec(spec)
                if kind == "ok":
                    found_ok = True
                    saw_nto_spec = True
                    continue
                if kind == "other":
                    continue
                saw_nto_spec = True
                notes.append(
                    _note(
                        "project.bad-spec",
                        "error",
                        f"qcc spec {spec} is not valid for SDP 8.0.",
                        detail,
                        path=rel,
                        line=statement.line,
                    )
                )
    if style == "plain" and not found_ok and not host_error and not saw_nto_spec:
        notes.append(
            _note(
                "plain.missing-target-spec",
                "error",
                "The Makefile uses qcc but never passes an SDP 8.0 -V spec.",
                "qcc defaults to the x86_64 driver. Set it explicitly, for example:\n"
                "  TARGET_ARCH = -Vgcc_ntoaarch64le\n"
                "The other SDP 8.0 spec is -Vgcc_ntox86_64. Put -V in TARGET_ARCH, CFLAGS, or the recipe.",
                path=_primary_makefile(parsed),
            )
        )
    elif style == "plain" and found_ok:
        notes.append(
            _note(
                "plain.target-spec",
                "ok",
                "The Makefile passes an SDP 8.0 qcc spec (gcc_ntoaarch64le or gcc_ntox86_64).",
            )
        )


def _check_preset_order(parsed: list[ParsedFile], root: Path, notes: list[Note]) -> None:
    warned = False
    saw_qtargets = False
    for item in parsed:
        qtargets_line = None
        for statement in item.statements:
            if "qtargets.mk" in include_kinds(statement):
                qtargets_line = statement.line
                break
        if qtargets_line is None:
            continue
        saw_qtargets = True
        late = []
        for statement in item.statements:
            if (
                statement.kind == "assign"
                and statement.name in PRESET_MACROS
                and statement.line > qtargets_line
            ):
                late.append(statement.name)
        if late:
            warned = True
            names = ", ".join(sorted(set(late)))
            notes.append(
                _note(
                    "mk.preset-after-qtargets",
                    "warning",
                    f"{names} is assigned after qtargets.mk.",
                    "Put NAME, SRCS, LIBS, and compiler flags above `include $(MKFILES_ROOT)/qtargets.mk`. "
                    "The SDP template reads those preset macros before including qtargets.",
                    path=_rel(root, item.path),
                    line=qtargets_line,
                )
            )
    if saw_qtargets and not warned:
        notes.append(
            _note(
                "mk.preset-order",
                "ok",
                "Preset macros are not assigned after qtargets.mk.",
            )
        )


def _check_variants(
    variants: list[Variant],
    parsed: list[ParsedFile],
    root: Path,
    notes: list[Note],
) -> None:
    if not variants:
        if any(item.path.name == "common.mk" for item in parsed):
            notes.append(
                _note(
                    "variant.none",
                    "error",
                    "common.mk is present but there are no variant directories.",
                    "Add a directory such as nto-aarch64-o-le or nto-x86_64-o with a Makefile that includes ../common.mk. "
                    "recurse.mk only builds subdirectories that contain a Makefile.",
                )
            )
        return

    parsed_by_dir = {}
    for item in parsed:
        parsed_by_dir.setdefault(item.path.parent.resolve(), []).append(item)

    healthy: list[str] = []
    saw_nto = False
    for variant in variants:
        rel = variant.name
        if variant.classic:
            notes.append(
                _note(
                    "variant.legacy-layout",
                    "warning",
                    f"{rel}/ is a nested CPU directory.",
                    "SDP 8.0 addvariant directories are flat: nto-aarch64-o-le or nto-x86_64-o.",
                    path=rel,
                )
            )
        if variant.os_name == "nto":
            saw_nto = True
        elif variant.os_name in {"linux", "win64"}:
            notes.append(
                _note(
                    "variant.host-os",
                    "info",
                    f"{rel} builds for the host OS ({variant.os_name}), not for Neutrino.",
                    path=rel,
                )
            )
        cpu_problem = _cpu_problem(variant)
        if cpu_problem:
            notes.append(
                _note(
                    "variant.cpu-unsupported",
                    "error",
                    f"{rel} is not an SDP 8.0 Neutrino CPU.",
                    cpu_problem + " Supported CPUs are aarch64 (little-endian) and x86_64.",
                    path=rel,
                )
            )
        elif _big_endian(variant):
            notes.append(
                _note(
                    "variant.big-endian",
                    "error",
                    f"{rel} requests big-endian output.",
                    "SDP 8.0 aarch64 and x86_64 targets are little-endian. Use nto-aarch64-o-le or nto-x86_64-o.",
                    path=rel,
                )
            )
        elif _missing_le(variant):
            notes.append(
                _note(
                    "variant.endian-suffix",
                    "info",
                    f"{rel} does not include the le variant.",
                    "SDP 8.0 examples spell the AArch64 executable directory nto-aarch64-o-le. "
                    "Little-endian is the only supported ARM endian.",
                    path=rel,
                )
            )
        if not cpu_problem and not _has_build_type(variant):
            notes.append(
                _note(
                    "variant.missing-build-type",
                    "warning",
                    f"{rel} has no build-type variant (o, so, dll, a, or a.shared).",
                    "An executable directory is nto-aarch64-o-le. A shared library is nto-x86_64-so.",
                    path=rel,
                )
            )

        makefile = _variant_makefile(variant.path)
        dnm = variant.path / "Makefile.dnm"
        if makefile is None:
            if dnm.is_file():
                notes.append(
                    _note(
                        "variant.do-not-make",
                        "info",
                        f"{rel} contains Makefile.dnm, so recurse.mk will skip it.",
                        path=rel,
                    )
                )
            else:
                notes.append(
                    _note(
                        "variant.no-makefile",
                        "warning",
                        f"{rel} has no Makefile, so recurse.mk will not build it.",
                        "Add a Makefile whose only job is `include ../common.mk`.",
                        path=rel,
                    )
                )
            continue
        variant_parsed = parsed_by_dir.get(variant.path.resolve(), [])
        if not any("common.mk" in include_kinds(statement) for item in variant_parsed for statement in item.statements):
            notes.append(
                _note(
                    "variant.missing-common",
                    "error",
                    f"{rel}/Makefile does not include common.mk.",
                    "The variant Makefile should be exactly `include ../common.mk` so the shared rules and qtargets.mk are used.",
                    path=f"{rel}/{makefile.name}",
                )
            )
        elif not cpu_problem and not _big_endian(variant) and variant.os_name == "nto" and _has_build_type(variant):
            healthy.append(rel)

    if variants and not saw_nto:
        notes.append(
            _note(
                "variant.no-neutrino",
                "warning",
                "None of the variant directories target Neutrino (nto).",
                "Host variants (linux, win64) do not produce a QNX OS binary. Add nto-aarch64-o-le or nto-x86_64-o.",
            )
        )
    if healthy and not any(note.severity in {"error", "warning"} and note.check_id.startswith("variant.") for note in notes):
        listed = ", ".join(healthy)
        notes.append(_note("variant.targets", "ok", f"Neutrino variant directories: {listed}."))
        if all(
            any("common.mk" in include_kinds(statement) for item in parsed_by_dir.get(variant.path.resolve(), []) for statement in item.statements)
            for variant in variants
            if _variant_makefile(variant.path) is not None
        ):
            notes.append(
                _note(
                    "variant.makefiles",
                    "ok",
                    "Each variant Makefile includes common.mk.",
                )
            )


def _check_text_pitfalls(parsed: list[ParsedFile], root: Path, notes: list[Note]) -> None:
    for item in parsed:
        rel = _rel(root, item.path)
        flagged_legacy = False
        flagged_march = False
        flagged_inc = False
        flagged_lib = False
        for statement in item.statements:
            blob = statement.text
            if not flagged_legacy and LEGACY_RE.search(blob):
                flagged_legacy = True
                notes.append(
                    _note(
                        "project.legacy-sdp-path",
                        "error",
                        "This makefile references an SDP 7 (or older) install path.",
                        "SDP 8.0 lives under ~/qnx800. The target tree is target/qnx or target/qnx8. qnx710 and target/qnx7 are the previous release.",
                        path=rel,
                        line=statement.line,
                    )
                )
            if not flagged_march and MARCH_RE.search(blob):
                flagged_march = True
                notes.append(
                    _note(
                        "project.march-native",
                        "error",
                        "The makefile passes -march=native or -mtune=native.",
                        "Those flags target the build machine. A QNX cross compile has to use the qcc spec (-Vgcc_ntoaarch64le or -Vgcc_ntox86_64) instead.",
                        path=rel,
                        line=statement.line,
                    )
                )
            if not flagged_inc and HOST_INC_RE.search(blob):
                flagged_inc = True
                notes.append(
                    _note(
                        "project.host-include",
                        "error",
                        "The makefile adds -I/usr/include.",
                        "That pulls in host Linux headers. qcc already searches $QNX_TARGET/usr/include. Remove the flag.",
                        path=rel,
                        line=statement.line,
                    )
                )
            if not flagged_lib and HOST_LIB_RE.search(blob):
                flagged_lib = True
                notes.append(
                    _note(
                        "project.host-lib",
                        "error",
                        "The makefile adds -L/usr/lib.",
                        "That can link host libraries into a Neutrino binary. Drop the flag and let qcc use QNX_TARGET.",
                        path=rel,
                        line=statement.line,
                    )
                )


def _check_recipe_indents(parsed: list[ParsedFile], root: Path, notes: list[Note]) -> None:
    for item in parsed:
        for line, text in item.indent_errors:
            notes.append(
                _note(
                    "make.recipe-spaces",
                    "error",
                    "A recipe line is indented with spaces. GNU make requires a tab.",
                    f"Line {line} starts with spaces: {text[:80]}",
                    path=_rel(root, item.path),
                    line=line,
                )
            )


def _check_destdir(parsed: list[ParsedFile], notes: list[Note], root: Path) -> None:
    blob = "\n".join(statement.text for item in parsed for statement in item.statements)
    if "DESTDIR" in blob:
        return
    if re.search(r"/(?:usr/local|usr)/(?:bin|lib)\b", blob) and re.search(r"\binstall\b", blob):
        notes.append(
            _note(
                "plain.destdir",
                "warning",
                "The install rule copies into /usr without $(DESTDIR).",
                "Cross builds should stage with `make DESTDIR=/tmp/stage install` (or DESTDIR=$QNX_TARGET/<cpu>). "
                "Do not install a Neutrino binary into the host /usr.",
                path=_primary_makefile(parsed),
            )
        )


def _check_listed_sources(
    parsed: list[ParsedFile],
    sources: list[Path],
    root: Path,
    notes: list[Note],
) -> None:
    names = {path.name for path in sources}
    for token in _merged_variables(parsed).get("SRCS", "").split():
        if not token or token.startswith(("$", "-", "%")):
            continue
        leaf = Path(token).name
        if (root / token).is_file() or leaf in names:
            continue
        notes.append(
            _note(
                "project.missing-source",
                "warning",
                f"SRCS lists {token}, but that file is not in the project tree.",
                "QNX mk builds run from the variant directory. Put sources at the project root and add "
                "`EXTRA_SRCVPATH+=$(PROJECT_ROOT)`, or fix the path.",
            )
        )


def _check_sources(
    sources: list[Path],
    parsed: list[ParsedFile],
    root: Path,
    notes: list[Note],
) -> None:
    libs = _collect_libs(parsed)
    builtins = [name for name in LIBC_BUILTINS if name in libs]
    if builtins:
        listed = ", ".join(builtins)
        lib_path, lib_line = _library_site(parsed, root, builtins)
        notes.append(
            _note(
                "link.libc-builtins",
                "warning",
                f"The link line pulls in {listed}, which libc already provides on QNX.",
                "Drop -lpthread, -ldl, and -lrt (and the mk tokens pthread, dl, and rt). "
                "Those libraries are not separate on SDP 8.0, and the link fails when they are missing from the sysroot.",
                path=lib_path,
                line=lib_line,
            )
        )
    socket_sites: list[tuple[str, int]] = []
    header_count = 0
    for path in sources:
        text = _read_text(path)
        if not text:
            continue
        rel = _rel(root, path)
        guarded = "__QNX__" in text or "__QNXNTO__" in text
        for line, cleaned in _clean_c_lines(text):
            include = INCLUDE_RE.match(cleaned)
            if include and header_count < 20:
                header = include.group(1).replace("\\", "/")
                severity, check_id, help_text = _header_finding(header)
                if check_id:
                    if guarded and severity == "error":
                        severity = "info"
                        help_text = help_text + " The file mentions __QNXNTO__ or __QNX__, so this may be inside a non-QNX ifdef."
                    elif guarded and severity == "warning":
                        severity = "info"
                    notes.append(
                        _note(check_id, severity, f"Includes {header}.", help_text, path=rel, line=line)
                    )
                    header_count += 1
            if SOCKET_RE.search(cleaned) and not any(site[0] == rel for site in socket_sites):
                socket_sites.append((rel, line))
    if socket_sites and "socket" not in libs:
        rel, line = socket_sites[0]
        if len(socket_sites) > 1:
            message = f"Socket APIs are used in {len(socket_sites)} files but the link line does not include libsocket."
        else:
            message = "Socket APIs are used but the link line does not include libsocket."
        notes.append(
            _note(
                "link.socket-missing",
                "warning",
                message,
                "QNX does not pull socket calls in from libc. For a mk project add `LIBS+=socket`. "
                "For a plain Makefile add `-lsocket` to LDLIBS.",
                path=rel,
                line=line,
            )
        )
    elif socket_sites:
        notes.append(_note("link.socket", "ok", "Socket APIs are linked with libsocket."))


def _check_scripts(root: Path, notes: list[Note]) -> None:
    for path in _iter_scripts(root):
        text = _read_text(path)
        if not text:
            continue
        rel = _rel(root, path)
        if LEGACY_RE.search(text):
            notes.append(
                _note(
                    "project.legacy-sdp-path",
                    "error",
                    "This script references an SDP 7 (or older) install path.",
                    "Point it at ~/qnx800/qnxsdp-env.sh. qnx710 is SDP 7.1.",
                    path=rel,
                )
            )
        if INVOKE_RE.search(text) and "qnxsdp-env" not in text and "QNX_HOST" not in text:
            notes.append(
                _note(
                    "script.sdk-env-not-sourced",
                    "warning",
                    f"{rel} runs a QNX build tool without sourcing qnxsdp-env.sh or setting QNX_HOST.",
                    "Source ~/qnx800/qnxsdp-env.sh in the same shell before make or qcc. "
                    "A fresh CI job does not inherit the variables from your laptop.",
                    path=rel,
                )
            )


def _check_cmake_advisory(cmake: Path, root: Path, notes: list[Note]) -> None:
    text = _read_text(cmake)
    if not _cmake_looks_like_qnx(cmake):
        notes.append(
            _note(
                "cmake.not-qnx",
                "warning",
                "CMakeLists.txt does not mention qcc or QNX.",
                "The Makefile was diagnosed. This CMake file would not cross-build for Neutrino as it stands.",
                path="CMakeLists.txt",
            )
        )
        return
    _specs_in_free_text(text, "CMakeLists.txt", notes)


def _check_cmake_body(cmake: Path, root: Path, notes: list[Note]) -> None:
    text = _read_text(cmake)
    if "qcc" not in text and "q++" not in text:
        notes.append(
            _note(
                "cmake.compiler",
                "warning",
                "CMakeLists.txt mentions QNX but does not name qcc or q++.",
                "Set CMAKE_C_COMPILER to qcc (and CMAKE_CXX_COMPILER to q++) in a toolchain file.",
                path="CMakeLists.txt",
            )
        )
    _specs_in_free_text(text, "CMakeLists.txt", notes)
    if LEGACY_RE.search(text):
        notes.append(
            _note(
                "project.legacy-sdp-path",
                "error",
                "CMakeLists.txt references an SDP 7 install path.",
                "Use the SDP 8.0 root (~/qnx800).",
                path="CMakeLists.txt",
            )
        )


def _specs_in_free_text(text: str, rel: str, notes: list[Note]) -> None:
    for spec in SPEC_RE.findall(text):
        kind, detail = describe_spec(spec)
        if kind in {"legacy", "unknown"}:
            notes.append(
                _note(
                    "project.bad-spec",
                    "error",
                    f"qcc spec {spec} is not valid for SDP 8.0.",
                    detail,
                    path=rel,
                )
            )


def _header_finding(header: str) -> tuple[str, str, str]:
    lowered = header.lower()
    if lowered in BAD_HEADERS:
        check_id, severity, help_text = BAD_HEADERS[lowered]
        return severity, check_id, help_text
    if lowered.startswith("linux/"):
        return (
            "error",
            "source.linux-header",
            "This is a Linux kernel header and is not in the QNX sysroot. Use Neutrino headers from $QNX_TARGET/usr/include.",
        )
    if lowered.startswith("bits/"):
        return (
            "error",
            "source.glibc-header",
            "bits/ headers are glibc internals. They are not shipped in the QNX sysroot.",
        )
    return "", "", ""


def _library_site(parsed: list[ParsedFile], root: Path, names: list[str]) -> tuple[str | None, int | None]:
    wanted = set(names)
    for item in parsed:
        for statement in item.statements:
            if statement.kind != "assign" or statement.name not in {"LIBS", "LDLIBS", "LDFLAGS", "LIBOPTS"}:
                continue
            tokens = _lib_tokens(statement.value, bare=statement.name == "LIBS")
            if tokens & wanted:
                return _rel(root, item.path), statement.line
    return None, None


def _collect_libs(parsed: list[ParsedFile]) -> set[str]:
    libs: set[str] = set()
    for item in parsed:
        for statement in item.statements:
            if statement.kind == "assign" and statement.name in {"LIBS", "LDLIBS", "LDFLAGS", "LIBOPTS"}:
                libs |= _lib_tokens(statement.value, bare=statement.name == "LIBS")
            elif statement.kind == "recipe":
                libs |= _lib_tokens(statement.text, bare=False)
    return libs


def _lib_tokens(text: str, *, bare: bool) -> set[str]:
    found: set[str] = set()
    for match in re.finditer(r"-l([A-Za-z0-9_+.]+)", text):
        found.add(_norm_lib(match.group(1)))
    if bare:
        for part in text.split():
            if part.startswith(("-", "$", "%")):
                continue
            found.add(_norm_lib(part))
    return found


def _norm_lib(name: str) -> str:
    if name.startswith("lib") and name[3:] in {"socket", "pthread", "dl", "rt", "m", "regex"}:
        return name[3:]
    return name


def _merged_variables(parsed: list[ParsedFile]) -> dict[str, str]:
    store: dict[str, str] = {}
    for item in parsed:
        for statement in item.statements:
            if statement.kind != "assign":
                continue
            if statement.op == "+=":
                current = store.get(statement.name, "")
                store[statement.name] = f"{current} {statement.value}".strip()
            elif statement.op == "?=":
                store.setdefault(statement.name, statement.value)
            else:
                store[statement.name] = statement.value
    return store


def compiler_kind(value: str) -> str:
    raw = value.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
        raw = raw[1:-1].strip()
    if not raw:
        return "empty"
    base = Path(raw.split()[0]).name.lower()
    if base.endswith(".exe"):
        base = base[:-4]
    if base in {"qcc", "q++"} or "qcc" in base:
        return "qcc"
    if base in {"gcc", "cc", "clang", "g++", "c++", "clang++"}:
        return "host"
    if "nto" in base or "qnx" in base:
        return "qcc"
    return "other"


def _host_compiler_help(style: str, variable: str) -> str:
    if style == "qnx-mk":
        return (
            f"Delete the {variable} assignment. qconfig.mk sets the driver to qcc, and the variant "
            "directory selects the CPU. Host gcc emits a Linux binary, not a Neutrino binary."
        )
    driver = "q++" if variable == "CXX" else "qcc"
    return (
        f"Set {variable} to {driver} and select the Neutrino target explicitly:\n"
        f"  {variable} = {driver}\n"
        "  TARGET_ARCH = -Vgcc_ntoaarch64le\n"
        "Host gcc and g++ emit Linux binaries. The other SDP 8.0 spec is -Vgcc_ntox86_64."
    )


def _variant_dirname(name: str) -> tuple[str, str, tuple[str, ...]] | None:
    parts = name.split("-")
    if len(parts) < 2 or parts[0] not in OS_NAMES:
        return None
    if parts[1] not in CPU_INFO:
        return None
    return parts[0], parts[1], tuple(parts[2:])


def _cpu_problem(variant: Variant) -> str | None:
    _canonical, problem = CPU_INFO.get(variant.cpu, (variant.cpu, f"CPU {variant.cpu} is not an SDP 8.0 target."))
    if problem and problem != "be":
        return problem
    if "v7" in variant.tokens:
        return "32-bit ARMv7 was removed in SDP 8.0. Use aarch64."
    return None


def _big_endian(variant: Variant) -> bool:
    _canonical, problem = CPU_INFO.get(variant.cpu, (variant.cpu, None))
    if problem == "be":
        return True
    return "be" in variant.tokens


def _missing_le(variant: Variant) -> bool:
    canonical, _problem = CPU_INFO.get(variant.cpu, (variant.cpu, None))
    if canonical != "aarch64" or variant.os_name != "nto":
        return False
    if variant.cpu in CPU_ENDIAN_IN_NAME or "le" in variant.tokens:
        return False
    if _big_endian(variant):
        return False
    return True


def _has_build_type(variant: Variant) -> bool:
    if variant.classic:
        return False
    return any(token in BUILD_TYPES for token in variant.tokens)


def _variant_makefile(path: Path) -> Path | None:
    for name in MAKEFILE_NAMES:
        candidate = path / name
        if candidate.is_file():
            return candidate
    return None


def _has_makefile(path: Path) -> bool:
    return _variant_makefile(path) is not None or (path / "Makefile.dnm").is_file()


def walk_sources(root: Path) -> list[Path]:
    found: list[Path] = []
    if not root.is_dir():
        return found
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if not name.startswith(".") and name not in SKIP_DIRS]
        if len(Path(dirpath).relative_to(root).parts) >= 3:
            dirnames[:] = []
        for name in filenames:
            if Path(name).suffix.lower() in SOURCE_EXTS:
                found.append(Path(dirpath) / name)
            if len(found) >= 200:
                return found
    return found


def _iter_scripts(root: Path) -> list[Path]:
    found: list[Path] = []
    for pattern in ("*.sh", "*/*.sh"):
        for path in root.glob(pattern):
            if path.is_file():
                found.append(path)
    workflows = root / ".github" / "workflows"
    if workflows.is_dir():
        for path in sorted(workflows.iterdir()):
            if path.is_file() and path.suffix in {".yml", ".yaml"}:
                found.append(path)
    return found


def _clean_c_lines(text: str) -> list[tuple[int, str]]:
    cleaned_lines: list[tuple[int, str]] = []
    in_block = False
    for lineno, line in enumerate(text.splitlines(), 1):
        pieces: list[str] = []
        index = 0
        while index < len(line):
            if in_block:
                end = line.find("*/", index)
                if end == -1:
                    index = len(line)
                    break
                in_block = False
                index = end + 2
                continue
            if line.startswith("/*", index):
                in_block = True
                index += 2
                continue
            if line.startswith("//", index):
                break
            pieces.append(line[index])
            index += 1
        cleaned_lines.append((lineno, "".join(pieces)))
    return cleaned_lines


def _read_text(path: Path) -> str:
    try:
        data = path.read_bytes()[:512_000]
    except OSError:
        return ""
    if b"\0" in data[:1024]:
        return ""
    return data.decode("utf-8", errors="replace")


def _within(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _rel(root: Path, path: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return path.name
    if not relative.parts:
        return "."
    return relative.as_posix()


def _primary_makefile(parsed: list[ParsedFile]) -> str | None:
    for item in parsed:
        if item.path.name in MAKEFILE_NAMES:
            return item.path.name
    if parsed:
        return parsed[0].path.name
    return None


def _rel_named(parsed: list[ParsedFile], root: Path, name: str) -> str | None:
    for item in parsed:
        if item.path.name == name:
            return _rel(root, item.path)
    return name if any(item.path.name == name for item in parsed) else None


def _assign_location(parsed: list[ParsedFile], root: Path, name: str) -> str | None:
    for item in parsed:
        for statement in item.statements:
            if statement.kind == "assign" and statement.name == name:
                return _rel(root, item.path)
    return None


def _assign_line(parsed: list[ParsedFile], name: str) -> int | None:
    for item in parsed:
        for statement in item.statements:
            if statement.kind == "assign" and statement.name == name:
                return statement.line
    return None


def _note(
    check_id: str,
    severity: str,
    message: str,
    help_text: str = "",
    path: str | None = None,
    line: int | None = None,
) -> Note:
    return Note(
        check_id=check_id,
        severity=severity,
        message=message,
        help=help_text,
        path=path,
        line=line,
        category="project",
    )
