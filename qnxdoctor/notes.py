"""Findings produced by the environment and project checks."""

from __future__ import annotations

from dataclasses import dataclass

SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2, "ok": 3}
CATEGORY_RANK = {"environment": 0, "project": 1}

# Within one severity, lead with the findings a person should read first.
DISPLAY_RANK = {
    "env.qnx-host-unset": 0,
    "env.qnx-host-missing": 1,
    "env.qnx-host-is-base": 1,
    "env.qnx-target-unset": 2,
    "env.qnx-target-missing": 3,
    "env.qcc-missing": 4,
    "env.qcc-not-on-path": 4,
    "env.qcc-without-host": 4,
    "env.qcc-shadowed": 4,
    "env.qxx-missing": 5,
    "env.makeflags-missing": 6,
    "env.mk-includes-unverified": 7,
    "env.mk-includes-missing": 7,
    "env.sdp-not-found": 8,
    "env.sdp-installed-not-sourced": 8,
    "env.sdp-wrong-version": 9,
    "env.mk-not-required": 10,
}


@dataclass(frozen=True)
class Note:
    check_id: str
    severity: str
    message: str
    help: str = ""
    path: str | None = None
    line: int | None = None
    category: str = "project"

    def with_severity(self, severity: str) -> Note:
        return Note(
            check_id=self.check_id,
            severity=severity,
            message=self.message,
            help=self.help,
            path=self.path,
            line=self.line,
            category=self.category,
        )


def sort_notes(notes: list[Note]) -> list[Note]:
    return sorted(
        notes,
        key=lambda note: (
            SEVERITY_RANK.get(note.severity, 9),
            CATEGORY_RANK.get(note.category, 9),
            DISPLAY_RANK.get(note.check_id, 50),
            note.path or "",
            note.line or 0,
            note.check_id,
            note.message,
        ),
    )
