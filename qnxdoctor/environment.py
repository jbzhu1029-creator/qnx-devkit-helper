"""Host-environment checks for an SDP 8.0 shell.

The filesystem is used only to see whether the paths named by the environment
exist. ``qcc`` is executed only when the caller asks for ``qcc -V`` and a
binary is already on PATH. Nothing is installed and no project recipe runs.
"""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path

from qnxdoctor.notes import Note
from qnxdoctor.sdp import SOURCE_COMMAND, SOURCE_HELP, VALID_SPECS, sdp_generation


TOOL_NAMES = ("qcc", "q++", "make", "mk", "mkifs", "mkqnximage")


@dataclass
class HostSnapshot:
    env: dict[str, str]
    home: Path
    system: str
    machine: str
    tools: dict[str, str | None]
    make_version: str | None
    qcc_dash_v: str | None
    search_roots: tuple[Path, ...]
    sdp_root: Path | None = None


def which(name: str, path_value: str) -> str | None:
    for directory in path_value.split(os.pathsep):
        if not directory:
            continue
        candidate = Path(directory) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def default_search_roots(home: Path, sdp_root: Path | None = None) -> tuple[Path, ...]:
    roots: list[Path] = []
    if sdp_root is not None:
        roots.append(sdp_root)
    roots.extend(
        [
            home / "qnx800",
            home / "qnx" / "qnx800",
            Path("/opt/qnx800"),
            Path("/opt/qnx/qnx800"),
            Path("/sdp/800"),
            home / "qnx710",
            home / "qnx700",
            Path("/opt/qnx710"),
            Path("/opt/qnx700"),
            Path("/sdp/710"),
            Path("/sdp/700"),
        ]
    )
    return tuple(roots)


def collect_snapshot(
    env: dict[str, str] | None = None,
    *,
    system: str | None = None,
    machine: str | None = None,
    sdp_root: Path | None = None,
    discover: bool = True,
    run_make: bool = True,
    run_qcc: bool = True,
) -> HostSnapshot:
    source = os.environ if env is None else env
    copied = {key: value for key, value in source.items()}
    system_name = system or platform.system()
    machine_name = machine or platform.machine()
    home = Path(copied.get("HOME") or copied.get("USERPROFILE") or str(Path.home()))
    path_value = copied.get("PATH", "")
    tools = {name: which(name, path_value) for name in TOOL_NAMES}
    if system_name == "Windows":
        for name in ("qcc", "q++"):
            if tools[name] is None:
                tools[name] = which(name + ".exe", path_value)
    return HostSnapshot(
        env=copied,
        home=home,
        system=system_name,
        machine=machine_name,
        tools=tools,
        make_version=_capture_make(tools.get("make")) if run_make else None,
        qcc_dash_v=_capture_qcc(tools.get("qcc")) if run_qcc else None,
        search_roots=default_search_roots(home, sdp_root) if discover else ((sdp_root,) if sdp_root else ()),
        sdp_root=sdp_root,
    )


def _capture_make(path: str | None) -> str | None:
    if not path:
        return None
    try:
        proc = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (proc.stdout or proc.stderr or "").strip() or None


def _capture_qcc(path: str | None) -> str | None:
    if not path:
        return None
    try:
        proc = subprocess.run(
            [path, "-V"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (proc.stdout or "") + (proc.stderr or "")


def _note(
    check_id: str,
    severity: str,
    message: str,
    help_text: str = "",
) -> Note:
    return Note(
        check_id=check_id,
        severity=severity,
        message=message,
        help=help_text,
        category="environment",
    )


def _qcc_name(system: str) -> str:
    return "qcc.exe" if system == "Windows" else "qcc"


def _qxx_name(system: str) -> str:
    return "q++.exe" if system == "Windows" else "q++"


def _host_qcc(host: Path, system: str) -> Path:
    return host / "usr" / "bin" / _qcc_name(system)


def _host_qxx(host: Path, system: str) -> Path:
    return host / "usr" / "bin" / _qxx_name(system)


def _candidate_qcc(base: Path, system: str) -> Path | None:
    if system == "Windows":
        relatives = (Path("host/win64/x86_64"), Path("host/win32/x86_64"))
        name = "qcc.exe"
    else:
        relatives = (Path("host/linux/x86_64"),)
        name = "qcc"
    for relative in relatives:
        candidate = base / relative / "usr" / "bin" / name
        if candidate.is_file():
            return candidate
    return None


def _host_os_mismatch(host: Path, system: str) -> bool:
    parts = {part.lower() for part in host.parts}
    if system == "Linux" and parts & {"win64", "win32", "darwin", "macos"}:
        return True
    if system == "Windows" and parts & {"linux", "darwin", "macos"}:
        return True
    return False


def _same_file(found: str | None, expected: Path) -> bool:
    if not found:
        return False
    try:
        return Path(found).resolve() == expected.resolve()
    except OSError:
        return os.path.normcase(os.path.normpath(found)) == os.path.normcase(os.path.normpath(str(expected)))


def _path_has_dir(path_value: str, directory: Path) -> bool:
    want = os.path.normcase(os.path.normpath(str(directory)))
    for entry in path_value.split(os.pathsep):
        if entry and os.path.normcase(os.path.normpath(entry)) == want:
            return True
    return False


def _i_paths(makeflags: str) -> list[str]:
    parts = makeflags.split()
    found: list[str] = []
    index = 0
    while index < len(parts):
        part = parts[index]
        if part == "-I" and index + 1 < len(parts):
            found.append(parts[index + 1])
            index += 2
            continue
        if part.startswith("-I") and len(part) > 2:
            found.append(part[2:])
        index += 1
    return found


def _same_path(left: str, right: Path) -> bool:
    try:
        if Path(left).exists() and right.exists():
            return Path(left).resolve() == right.resolve()
    except OSError:
        pass
    return os.path.normcase(os.path.normpath(left)) == os.path.normcase(os.path.normpath(str(right)))


def _first_file(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.is_file():
            return path
    return None


def _read_banner(root: Path) -> str:
    for name in ("qnxsdp-env.sh", "qnxsdp-env.bat"):
        script = root / name
        if script.is_file():
            try:
                return script.read_text(encoding="utf-8", errors="replace")[:4000]
            except OSError:
                return ""
    return ""


def classify_install(root: Path) -> str | None:
    """Return ``8``, ``7``, ``unknown``, or None when ``root`` is not an SDP tree."""

    if not root.exists() or not root.is_dir():
        return None
    banner = _read_banner(root)
    has_shape = bool(banner) or (root / "host").is_dir()
    if not has_shape:
        return None
    if "8.0" in banner and "7.1" not in banner and "7.0" not in banner:
        return "8"
    if ("7.1" in banner or "7.0" in banner) and "8.0" not in banner:
        return "7"
    generation = sdp_generation(str(root))
    if generation == "8":
        return "8"
    if generation == "7":
        return "7"
    lowered = root.name.lower()
    if lowered in {"qnx800", "800"}:
        return "8"
    if lowered in {"qnx710", "qnx700", "710", "700"}:
        return "7"
    if (root / "target" / "qnx8").is_dir() or (root / "target" / "qnx").is_dir():
        if not (root / "target" / "qnx7").is_dir():
            return "8"
    return "unknown"


def _platform_note(snapshot: HostSnapshot) -> Note | None:
    machine = snapshot.machine.lower()
    if snapshot.system == "Darwin":
        return _note(
            "env.host-unsupported",
            "warning",
            "This host is macOS. SDP 8.0 ships host tools for x86_64 Linux and 64-bit Windows only.",
            "Use a Linux x86_64 or Windows x64 machine, or a VM. QEMU is a fine Neutrino target, but the compiler still runs on the host.",
        )
    if snapshot.system == "Linux" and machine not in {"x86_64", "amd64"}:
        return _note(
            "env.host-unsupported",
            "warning",
            f"This host CPU is {snapshot.machine}. SDP 8.0 host tools are built for x86_64, not for ARM hosts.",
        )
    if snapshot.system == "Windows" and machine not in {"x86_64", "amd64"}:
        return _note(
            "env.host-unsupported",
            "warning",
            f"This host CPU is {snapshot.machine}. SDP 8.0 Windows host tools are x64 only.",
        )
    if snapshot.system not in {"Linux", "Windows"}:
        return _note(
            "env.host-unsupported",
            "warning",
            f"SDP 8.0 does not publish host tools for {snapshot.system}.",
        )
    return None


def _target_include(target: Path) -> Path | None:
    include = target / "usr" / "include"
    if include.is_dir():
        return include
    return None


def _nested_target_include(base: Path) -> Path | None:
    for relative in ("target/qnx/usr/include", "target/qnx8/usr/include"):
        include = base / relative
        if include.is_dir():
            return include
    return None


def evaluate_environment(snapshot: HostSnapshot) -> list[Note]:
    notes: list[Note] = []
    env = snapshot.env
    platform_note = _platform_note(snapshot)
    if platform_note is not None:
        notes.append(platform_note)

    host_raw = env.get("QNX_HOST", "").strip()
    target_raw = env.get("QNX_TARGET", "").strip()
    host_path = Path(host_raw) if host_raw else None
    target_path = Path(target_raw) if target_raw else None
    host_ok = False
    target_include: Path | None = None

    if host_path is None:
        notes.append(
            _note(
                "env.qnx-host-unset",
                "warning",
                "QNX_HOST is not set.",
                SOURCE_HELP,
            )
        )
    elif not host_path.is_dir():
        notes.append(
            _note(
                "env.qnx-host-missing",
                "error",
                f"QNX_HOST does not exist: {host_path}",
                "Point QNX_HOST at the host tree, usually ~/qnx800/host/linux/x86_64, or source qnxsdp-env.sh.",
            )
        )
    else:
        qcc_file = _host_qcc(host_path, snapshot.system)
        if not qcc_file.is_file():
            nested = _candidate_qcc(host_path, snapshot.system)
            if nested is not None:
                host_tree = nested.parents[2]
                notes.append(
                    _note(
                        "env.qnx-host-is-base",
                        "error",
                        f"QNX_HOST points at {host_path}, which looks like the SDP root rather than the host tree.",
                        f"Set QNX_HOST={host_tree} or source {host_path / 'qnxsdp-env.sh'}.",
                    )
                )
            else:
                notes.append(
                    _note(
                        "env.qnx-host-missing",
                        "error",
                        f"QNX_HOST has no usr/bin/{_qcc_name(snapshot.system)}: {host_path}",
                        "QNX_HOST should be the host tool tree (host/linux/x86_64 on Linux), not target/ and not a partial unpack.",
                    )
                )
        elif _host_os_mismatch(host_path, snapshot.system):
            notes.append(
                _note(
                    "env.host-os-mismatch",
                    "error",
                    f"QNX_HOST is {host_path}, which does not match this {snapshot.system} machine.",
                    "Source the env script on the machine where the host tools were installed. A Windows host tree will not run on Linux.",
                )
            )
        else:
            host_ok = True
            notes.append(_note("env.qnx-host", "ok", f"QNX_HOST is {host_path}."))

    if target_path is None:
        notes.append(
            _note(
                "env.qnx-target-unset",
                "warning",
                "QNX_TARGET is not set.",
                "qnxsdp-env.sh sets this to the Neutrino sysroot, either target/qnx or target/qnx8 under the SDP root. qcc and qconfig.mk both use it.",
            )
        )
    elif not target_path.is_dir():
        notes.append(
            _note(
                "env.qnx-target-missing",
                "error",
                f"QNX_TARGET does not exist: {target_path}",
            )
        )
    else:
        include = _target_include(target_path)
        if include is None:
            nested = _nested_target_include(target_path)
            if nested is not None:
                notes.append(
                    _note(
                        "env.qnx-target-is-base",
                        "error",
                        f"QNX_TARGET points at {target_path}, but the sysroot include directory is {nested}.",
                        "QNX_TARGET must be the directory that contains usr/include (target/qnx or target/qnx8), not the SDP root.",
                    )
                )
            else:
                notes.append(
                    _note(
                        "env.qnx-target-not-tree",
                        "error",
                        f"QNX_TARGET has no usr/include directory: {target_path}",
                        "Use the SDP 8.0 target tree (target/qnx or target/qnx8). An empty directory will not satisfy qconfig.mk.",
                    )
                )
        else:
            target_include = include
            notes.append(_note("env.qnx-target", "ok", f"QNX_TARGET is {target_path}."))

    host_gen = sdp_generation(str(host_path)) if host_path is not None else None
    target_gen = sdp_generation(str(target_path)) if target_path is not None else None
    bad_gen = {host_gen, target_gen} & {"7", "mixed"}
    disagree = bool(host_gen and target_gen and host_gen != target_gen)
    if bad_gen or disagree:
        if disagree and not bad_gen:
            message = f"QNX_HOST looks like SDP {host_gen} but QNX_TARGET looks like SDP {target_gen}."
        else:
            message = "QNX_HOST or QNX_TARGET points at SDP 7. qnxdoctor checks SDP 8.0 projects."
        notes.append(
            _note(
                "env.sdp-wrong-version",
                "error",
                message,
                "Source ~/qnx800/qnxsdp-env.sh. qnx710 and target/qnx7 belong to the previous release.",
            )
        )

    _check_compilers(snapshot, notes, host_ok, host_path)
    _check_makeflags(snapshot, notes, target_include)
    _check_mk_includes(notes, target_include)
    _check_leaks(env, notes)
    _check_make(snapshot, notes)
    _check_mk_binary(snapshot, notes)
    # Discovery is a hint for a shell that has not activated the SDP.
    # A shell that already points QNX_HOST at a real host tree gets the
    # specific path errors above instead of "not sourced".
    if not host_ok or target_path is None:
        _check_discovery(snapshot, notes)
    _check_qcc_specs(snapshot, notes)
    return notes


def _check_compilers(
    snapshot: HostSnapshot,
    notes: list[Note],
    host_ok: bool,
    host_path: Path | None,
) -> None:
    tool = snapshot.tools.get("qcc")
    path_value = snapshot.env.get("PATH", "")
    if host_ok and host_path is not None:
        expected = _host_qcc(host_path, snapshot.system)
        if tool and _same_file(tool, expected):
            notes.append(_note("env.qcc", "ok", f"qcc is {tool}."))
            if _path_has_dir(path_value, expected.parent):
                notes.append(_note("env.path", "ok", f"PATH includes {expected.parent}."))
            else:
                notes.append(
                    _note(
                        "env.path-missing-host-bin",
                        "warning",
                        f"qcc was found, but PATH does not list {expected.parent}.",
                        "qnxsdp-env.sh prepends $QNX_HOST/usr/bin. A later directory can shadow qcc if that entry is missing.",
                    )
                )
        elif expected.is_file() and not tool:
            notes.append(
                _note(
                    "env.qcc-not-on-path",
                    "warning",
                    f"qcc exists at {expected} but is not on PATH.",
                    SOURCE_HELP,
                )
            )
        elif tool and expected.is_file():
            notes.append(
                _note(
                    "env.qcc-shadowed",
                    "error",
                    f"PATH finds qcc at {tool}, not the SDP driver at {expected}.",
                    "Put $QNX_HOST/usr/bin ahead of other entries before building.",
                )
            )
        else:
            notes.append(
                _note(
                    "env.qcc-missing",
                    "warning",
                    "qcc is not on PATH.",
                    "qcc is the QNX C and C++ driver. Sourcing qnxsdp-env.sh puts it on PATH. No target board is required to check a project.",
                )
            )
    elif not tool:
        notes.append(
            _note(
                "env.qcc-missing",
                "warning",
                "qcc is not on PATH.",
                "qcc is the QNX C and C++ driver. Sourcing qnxsdp-env.sh puts it on PATH. File checks do not need it.",
            )
        )
    else:
        notes.append(
            _note(
                "env.qcc-without-host",
                "warning",
                f"qcc is on PATH at {tool}, but QNX_HOST is not set.",
                "The driver uses QNX_HOST and QNX_TARGET to find headers and libraries. Source qnxsdp-env.sh rather than copying qcc onto PATH by itself.",
            )
        )

    qxx = snapshot.tools.get("q++")
    if host_ok and host_path is not None:
        expected_xx = _host_qxx(host_path, snapshot.system)
        if qxx:
            notes.append(_note("env.qxx", "ok", f"q++ is {qxx}."))
        elif expected_xx.is_file():
            notes.append(
                _note(
                    "env.qxx-missing",
                    "warning",
                    f"q++ exists at {expected_xx} but is not on PATH.",
                    "C++ projects use q++. It is installed next to qcc.",
                )
            )
        else:
            notes.append(
                _note(
                    "env.qxx-missing",
                    "warning",
                    f"QNX_HOST has no {_qxx_name(snapshot.system)}.",
                    "C++ projects need q++. A C-only tree can ignore this warning.",
                )
            )
    elif not qxx:
        notes.append(
            _note(
                "env.qxx-missing",
                "warning",
                "q++ is not on PATH.",
                "q++ is the C++ driver and lives next to qcc after qnxsdp-env.sh is sourced.",
            )
        )


def _check_makeflags(snapshot: HostSnapshot, notes: list[Note], target_include: Path | None) -> None:
    makeflags = snapshot.env.get("MAKEFLAGS", "")
    if target_include is not None:
        if any(_same_path(entry, target_include) for entry in _i_paths(makeflags)):
            notes.append(
                _note(
                    "env.makeflags",
                    "ok",
                    f"MAKEFLAGS includes -I{target_include}.",
                )
            )
        else:
            shown = makeflags if makeflags else "(empty)"
            notes.append(
                _note(
                    "env.makeflags-missing",
                    "error",
                    f"MAKEFLAGS does not include -I{target_include} (MAKEFLAGS is {shown}).",
                    "Without that -I path, `include $(QCONFIG)` cannot find qconfig.mk. qnxsdp-env.sh sets it. Exporting QNX_TARGET alone is not enough.",
                )
            )
        return
    notes.append(
        _note(
            "env.makeflags-missing",
            "warning",
            "MAKEFLAGS cannot point at the SDP include directory until QNX_TARGET is set.",
            "The recursive mk system finds qconfig.mk because MAKEFLAGS contains -I$QNX_TARGET/usr/include. qnxsdp-env.sh sets both.",
        )
    )


def _check_mk_includes(notes: list[Note], target_include: Path | None) -> None:
    if target_include is None:
        notes.append(
            _note(
                "env.mk-includes-unverified",
                "warning",
                "qconfig.mk, qtargets.mk, and recurse.mk were not verified because QNX_TARGET is unset or has no usr/include.",
                "Those files live under $QNX_TARGET/usr/include and $QNX_TARGET/usr/include/mk. They are the 'mk' in a QNX build. There is no separate mk compiler in SDP 8.0.",
            )
        )
        return
    missing: list[str] = []
    qconfig = _first_file(
        [
            target_include / "qconfig.mk",
            target_include / "mk" / "qconfig.mk",
            target_include / "mk" / "qconf-linux.mk",
            target_include / "mk" / "qconf-win32.mk",
            target_include / "mk" / "qconf-win64.mk",
        ]
    )
    qtargets = _first_file(
        [target_include / "mk" / "qtargets.mk", target_include / "qtargets.mk"]
    )
    recurse = _first_file(
        [target_include / "mk" / "recurse.mk", target_include / "recurse.mk"]
    )
    if qconfig is None:
        missing.append("qconfig.mk")
    if qtargets is None:
        missing.append("qtargets.mk")
    if recurse is None:
        missing.append("recurse.mk")
    if missing:
        listed = ", ".join(missing)
        notes.append(
            _note(
                "env.mk-includes-missing",
                "error",
                f"The SDP mk includes are incomplete under {target_include}: missing {listed}.",
                "A full target tree has qconfig.mk (or a qconf-<host>.mk) plus mk/qtargets.mk and mk/recurse.mk. Reinstall the SDP 8.0 target component if these were left out.",
            )
        )
    else:
        notes.append(
            _note(
                "env.mk-includes",
                "ok",
                f"qconfig.mk, qtargets.mk, and recurse.mk are under {target_include}.",
            )
        )


def _check_leaks(env: dict[str, str], notes: list[Note]) -> None:
    for variable in ("CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH"):
        value = env.get(variable, "")
        if value and "/usr/include" in value.replace("\\", "/"):
            notes.append(
                _note(
                    "env.host-include-leak",
                    "error",
                    f"{variable} contains /usr/include, which injects host headers into qcc.",
                    f"Unset {variable} before building. qcc already searches the Neutrino sysroot from QNX_TARGET.",
                )
            )
    library_path = env.get("LIBRARY_PATH", "")
    if library_path and "/usr/lib" in library_path.replace("\\", "/"):
        notes.append(
            _note(
                "env.host-lib-leak",
                "error",
                "LIBRARY_PATH contains /usr/lib, which can pull host libraries into a QNX link.",
                "Unset LIBRARY_PATH before building. QNX libraries come from QNX_TARGET.",
            )
        )


def _check_make(snapshot: HostSnapshot, notes: list[Note]) -> None:
    make = snapshot.tools.get("make")
    if not make:
        notes.append(
            _note(
                "env.make-missing",
                "warning",
                "GNU make is not on PATH.",
                "The QNX mk system is GNU make plus the SDP *.mk files. Install GNU make. You do not need a program named mk.",
            )
        )
        return
    version = snapshot.make_version
    if version is None:
        notes.append(_note("env.make", "ok", f"make is on PATH at {make}."))
        return
    first = version.splitlines()[0].strip()
    if "GNU Make" in version:
        notes.append(
            _note(
                "env.make",
                "ok",
                f"{first} at {make}. The QNX mk system uses GNU make.",
            )
        )
    else:
        notes.append(
            _note(
                "env.make-not-gnu",
                "error",
                f"make at {make} does not report GNU Make ({first}).",
                "Recursive QNX makefiles need GNU make. BSD make will not do.",
            )
        )


def _check_mk_binary(snapshot: HostSnapshot, notes: list[Note]) -> None:
    found = snapshot.tools.get("mk")
    if found:
        notes.append(
            _note(
                "env.mk-binary",
                "info",
                f"A program named mk is on PATH at {found}. SDP 8.0 does not use it as the compiler.",
                "Builds go through GNU make, qcc, and the mk include files (qconfig.mk, qtargets.mk, recurse.mk).",
            )
        )
        return
    notes.append(
        _note(
            "env.mk-not-required",
            "info",
            "No mk executable is on PATH. That is expected for SDP 8.0.",
            "There is no mk compiler. The mk build system is GNU make plus qconfig.mk, qtargets.mk, and recurse.mk under $QNX_TARGET/usr/include.",
        )
    )


def _display_path(path: Path, home: Path) -> str:
    try:
        relative = path.relative_to(home)
    except ValueError:
        return str(path)
    text = relative.as_posix()
    if text == ".":
        return "~"
    return "~/" + text


def _check_discovery(snapshot: HostSnapshot, notes: list[Note]) -> None:
    found8: list[Path] = []
    found7: list[Path] = []
    user_root = snapshot.sdp_root
    if user_root is not None and not user_root.exists():
        notes.append(
            _note(
                "env.sdp-root-missing",
                "error",
                f"--sdp-root does not exist: {user_root}",
            )
        )
        return

    seen: set[Path] = set()
    for root in snapshot.search_roots:
        try:
            key = root.resolve() if root.exists() else root
        except OSError:
            key = root
        if key in seen:
            continue
        seen.add(key)
        kind = classify_install(root)
        if kind == "8":
            found8.append(root)
        elif kind == "7":
            found7.append(root)
        elif user_root is not None and root == user_root:
            notes.append(
                _note(
                    "env.sdp-root-invalid",
                    "error",
                    f"--sdp-root is not an SDP tree: {user_root}",
                    "Pass the directory that contains qnxsdp-env.sh, for example ~/qnx800.",
                )
            )
            return

    if found8:
        listed = ", ".join(_display_path(path, snapshot.home) for path in found8)
        script = _display_path(found8[0] / "qnxsdp-env.sh", snapshot.home)
        notes.append(
            _note(
                "env.sdp-installed-not-sourced",
                "warning",
                f"SDP 8.0 looks installed at {listed}, but this shell has not activated it.",
                f"  source {script}\n"
                "Sourcing the script, not merely having the directory, is what sets QNX_HOST, QNX_TARGET, PATH, and MAKEFLAGS.",
            )
        )
        return
    if found7:
        listed = ", ".join(_display_path(path, snapshot.home) for path in found7)
        notes.append(
            _note(
                "env.sdp-wrong-version",
                "warning",
                f"Found SDP 7 at {listed}, and no SDP 8.0 tree.",
                "This doctor targets SDP 8.0 (~/qnx800). SDP 7.1 uses qnx710 and does not support the same target set (ARMv7 was removed in 8.0).",
            )
        )
        return
    if user_root is not None:
        return
    if not snapshot.search_roots:
        notes.append(
            _note(
                "env.sdp-not-found",
                "warning",
                "No SDP install prefixes were scanned.",
                "Pass --sdp-root ~/qnx800, or drop --no-discover so the usual locations are checked. File diagnosis does not need the SDP.",
            )
        )
        return
    preview = ", ".join(_display_path(path, snapshot.home) for path in snapshot.search_roots[:6])
    notes.append(
        _note(
            "env.sdp-not-found",
            "warning",
            "No QNX SDP directory was found in the usual install locations.",
            "Looked at "
            + preview
            + ". Install SDP 8.0 (QNX Everywhere or a licensed SDP) and "
            + SOURCE_COMMAND
            + ". Judges and CI can still run the project checks without it.",
        )
    )


def _check_qcc_specs(snapshot: HostSnapshot, notes: list[Note]) -> None:
    if not snapshot.tools.get("qcc"):
        return
    listing = snapshot.qcc_dash_v
    if listing is None:
        return
    if not listing.strip():
        notes.append(
            _note(
                "env.qcc-specs-unlisted",
                "info",
                "qcc -V did not return a compiler list, so the installed specs were not checked.",
            )
        )
        return
    found = [spec for spec in VALID_SPECS if spec in listing]
    if set(found) == set(VALID_SPECS):
        notes.append(
            _note(
                "env.qcc-specs",
                "ok",
                "qcc reports the SDP 8.0 specs gcc_ntoaarch64le and gcc_ntox86_64.",
            )
        )
    elif found:
        missing = [spec for spec in VALID_SPECS if spec not in found]
        notes.append(
            _note(
                "env.qcc-specs-incomplete",
                "warning",
                f"qcc reports {', '.join(found)} but not {', '.join(missing)}.",
                "SDP 8.0 ships both AArch64 little-endian and x86_64. A partial unpack will fail when the project builds the missing one.",
            )
        )
    else:
        notes.append(
            _note(
                "env.qcc-specs-unknown",
                "warning",
                "qcc -V output did not mention gcc_ntoaarch64le or gcc_ntox86_64.",
                "That usually means the driver on PATH is not an SDP 8.0 qcc.",
            )
        )
    if "gcc_ntoarmv7le" in listing:
        notes.append(
            _note(
                "env.qcc-legacy-spec",
                "warning",
                "qcc still advertises gcc_ntoarmv7le, which SDP 8.0 does not support.",
                "Do not target ARMv7. Use gcc_ntoaarch64le or gcc_ntox86_64.",
            )
        )
