"""Combine the host-environment and project reports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qnxdoctor.environment import HostSnapshot, evaluate_environment
from qnxdoctor.notes import Note, sort_notes
from qnxdoctor.project import diagnose_project
from qnxdoctor.sdp import DEGRADED_IDS, REQUIRE_SDP_IDS


@dataclass
class Report:
    project: str
    style: str
    mode: str
    notes: list[Note]
    require_sdp: bool = False

    def displayed(self) -> list[Note]:
        shown: list[Note] = []
        for note in self.notes:
            if self.require_sdp and note.severity == "warning" and note.check_id in REQUIRE_SDP_IDS:
                shown.append(note.with_severity("error"))
            else:
                shown.append(note)
        return sort_notes(shown)

    def counts(self) -> dict[str, int]:
        counts = {"error": 0, "warning": 0, "info": 0, "ok": 0}
        for note in self.displayed():
            counts[note.severity] = counts.get(note.severity, 0) + 1
        return counts

    @property
    def status(self) -> str:
        return "fail" if self.counts()["error"] else "pass"


def diagnose(path: Path | str, snapshot: HostSnapshot, *, require_sdp: bool = False) -> Report:
    project = diagnose_project(Path(path))
    env_notes = evaluate_environment(snapshot)
    mode = "ready"
    for note in env_notes:
        if note.severity == "error" or (note.severity == "warning" and note.check_id in DEGRADED_IDS):
            mode = "degraded"
            break
    return Report(
        project=display_path(project.root),
        style=project.style,
        mode=mode,
        notes=[*project.notes, *env_notes],
        require_sdp=require_sdp,
    )


def display_path(path: Path) -> str:
    try:
        resolved = path.resolve() if path.exists() else path
    except OSError:
        resolved = path
    try:
        relative = Path(resolved).resolve().relative_to(Path.cwd().resolve()) if Path(resolved).exists() else None
    except (OSError, ValueError):
        relative = None
    if relative is None:
        try:
            relative = Path(resolved).relative_to(Path.cwd())
        except ValueError:
            return str(path)
    if not relative.parts:
        return "."
    return relative.as_posix()
