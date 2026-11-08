"""Text and JSON renderers for a diagnosis report."""

from __future__ import annotations

import json
import textwrap

from qnxdoctor import __version__
from qnxdoctor.diagnose import Report
from qnxdoctor.notes import Note
from qnxdoctor.sdp import SDP_VERSION

LABELS = {"error": "ERROR", "warning": "WARN", "info": "INFO", "ok": "OK"}
COLORS = {
    "error": "\033[31m",
    "warning": "\033[33m",
    "info": "\033[36m",
    "ok": "\033[32m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}


def render_text(report: Report, *, color: bool = False, quiet: bool = False) -> str:
    counts = report.counts()
    if quiet:
        return (
            f"qnxdoctor {__version__}  {report.project}  {report.style}  {report.mode}  "
            f"{report.status}  {_plural(counts['error'], 'error', 'errors')}, "
            f"{_plural(counts['warning'], 'warning', 'warnings')}, "
            f"{_plural(counts['info'], 'note', 'notes')}, "
            f"{_plural(counts['ok'], 'passed check', 'passed')}\n"
        )

    def paint(text: str, name: str | None = None, bold: bool = False) -> str:
        if not color:
            return text
        prefix = ""
        if bold:
            prefix += COLORS["bold"]
        if name:
            prefix += COLORS[name]
        if not prefix:
            return text
        return f"{prefix}{text}{COLORS['reset']}"

    lines = [
        paint(f"qnxdoctor {__version__} | QNX SDP {SDP_VERSION} host doctor", bold=True),
        f"project : {report.project}",
        f"style   : {report.style}",
        f"mode    : {report.mode}",
        f"status  : {paint(report.status, 'ok' if report.status == 'pass' else 'error')}",
        "",
    ]
    shown = report.displayed()
    for category, title in (("environment", "Environment"), ("project", "Project")):
        lines.append(paint(title, bold=True))
        problems = [note for note in shown if note.category == category and note.severity != "ok"]
        if not problems:
            lines.append("  (no problems)")
        else:
            for note in problems:
                lines.extend(_format_note(note, paint))
        lines.append("")

    passed = [note for note in shown if note.severity == "ok"]
    if passed:
        lines.append(paint("Passed", bold=True))
        for note in passed:
            lines.extend(_format_note(note, paint))
        lines.append("")

    lines.append(
        "Summary: "
        + ", ".join(
            (
                _plural(counts["error"], "error", "errors"),
                _plural(counts["warning"], "warning", "warnings"),
                _plural(counts["info"], "note", "notes"),
                _plural(counts["ok"], "passed check", "passed"),
            )
        )
    )
    return "\n".join(lines) + "\n"


def render_json(report: Report) -> str:
    shown = report.displayed()
    findings = []
    passed = []
    for note in shown:
        payload = _json_note(note, promoted=_promoted(report, note))
        if note.severity == "ok":
            passed.append(payload)
        else:
            findings.append(payload)
    document = {
        "tool": "qnxdoctor",
        "version": __version__,
        "sdp": SDP_VERSION,
        "project": report.project,
        "style": report.style,
        "mode": report.mode,
        "status": report.status,
        "require_sdp": report.require_sdp,
        "summary": report.counts(),
        "findings": findings,
        "passed": passed,
    }
    return json.dumps(document, indent=2) + "\n"


def _promoted(report: Report, shown: Note) -> bool:
    if not report.require_sdp or shown.severity != "error":
        return False
    for original in report.notes:
        if original.check_id == shown.check_id and original.message == shown.message and original.line == shown.line:
            return original.severity == "warning"
    return False


def _json_note(note: Note, *, promoted: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": note.check_id,
        "severity": note.severity,
        "category": note.category,
        "message": note.message,
    }
    if note.help:
        payload["help"] = note.help
    if note.path:
        payload["path"] = note.path
    if note.line:
        payload["line"] = note.line
    if promoted:
        payload["promoted"] = True
    return payload


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _format_note(note: Note, paint) -> list[str]:
    label = LABELS.get(note.severity, note.severity.upper())
    where = ""
    if note.path and note.line:
        where = f"  {note.path}:{note.line}"
    elif note.path:
        where = f"  {note.path}"
    lines = [f"  {paint(label, note.severity)}  {note.check_id}{where}"]
    lines.extend(
        textwrap.wrap(
            note.message,
            width=78,
            initial_indent="       ",
            subsequent_indent="       ",
            break_on_hyphens=False,
        )
        or ["       " + note.message]
    )
    if note.help:
        lines.extend(_wrap_help(note.help))
    return lines


def _wrap_help(help_text: str) -> list[str]:
    lines: list[str] = []
    for paragraph in help_text.split("\n"):
        if paragraph.startswith("  "):
            lines.append("       " + paragraph.rstrip())
            continue
        stripped = paragraph.strip()
        if not stripped:
            continue
        lines.extend(
            textwrap.wrap(
                stripped,
                width=78,
                initial_indent="       ",
                subsequent_indent="       ",
                break_on_hyphens=False,
            )
        )
    return lines
