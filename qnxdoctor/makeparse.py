"""Text-only Makefile reader.

Recipes are never executed. Make conditionals are not evaluated: an assignment
inside ``ifeq`` is still visible, which is what we want when a Neutrino build
might pick it up. ``define``/``endef`` bodies are skipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

ASSIGN_RE = re.compile(
    r"^(?:override\s+)?(?:export\s+)?(?:override\s+)?"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*(\?=|\+=|:=|=)\s*(.*)$"
)
INCLUDE_RE = re.compile(r"^(?:-?include|sinclude)\s+(.+)$")


def strip_comment(line: str) -> str:
    """Drop an unquoted ``#`` comment, honoring backslash escapes."""

    out: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(line):
        char = line[i]
        if char == "\\" and i + 1 < len(line):
            out.append(char)
            out.append(line[i + 1])
            i += 2
            continue
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            break
        out.append(char)
        i += 1
    return "".join(out)


def continues_line(line: str) -> bool:
    """True when the line has an odd number of trailing backslashes."""

    count = 0
    for char in reversed(line):
        if char == "\\":
            count += 1
        else:
            break
    return count % 2 == 1


def looks_like_rule(logical: str) -> bool:
    if not logical:
        return False
    head = logical.split(None, 1)[0]
    if head in {"ifeq", "ifneq", "ifdef", "ifndef", "else", "endif", "include", "-include", "sinclude"}:
        return False
    if ASSIGN_RE.match(logical):
        return False
    left, sep, _right = logical.partition(":")
    if not sep or "=" in left:
        return False
    return True


@dataclass
class Statement:
    line: int
    kind: str
    text: str
    name: str = ""
    op: str = ""
    value: str = ""


@dataclass
class ParsedFile:
    path: Path
    statements: list[Statement] = field(default_factory=list)
    defines: set[str] = field(default_factory=set)
    indent_errors: list[tuple[int, str]] = field(default_factory=list)

    def variables(self) -> dict[str, str]:
        store: dict[str, str] = {}
        for statement in self.statements:
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


def parse_makefile(path: Path, text: str | None = None) -> ParsedFile:
    if text is None:
        text = path.read_text(encoding="utf-8", errors="replace")
    raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    parsed = ParsedFile(path=path)
    in_define = False
    prev_rule = False
    index = 0
    total = len(raw_lines)
    while index < total:
        lineno = index + 1
        line = raw_lines[index]
        if line.strip() == "":
            prev_rule = False
            index += 1
            continue
        if in_define:
            if line.strip() == "endef":
                in_define = False
            index += 1
            continue
        stripped = line.strip()
        if stripped == "define" or stripped.startswith("define "):
            parts = stripped.split()
            if len(parts) >= 2:
                parsed.defines.add(parts[1])
            in_define = True
            index += 1
            prev_rule = False
            continue

        group: list[tuple[int, str]] = [(lineno, line)]
        while continues_line(group[-1][1]) and index + 1 < total:
            index += 1
            group.append((index + 1, raw_lines[index]))
        index += 1

        chunks: list[str] = []
        for _number, physical in group:
            piece = physical
            if continues_line(piece):
                piece = piece[:-1]
            chunks.append(strip_comment(piece).strip())
        logical = " ".join(chunk for chunk in chunks if chunk).strip()
        if not logical:
            continue

        first = group[0][1]
        if first.startswith(" ") and not first.startswith("\t"):
            if prev_rule and not ASSIGN_RE.match(logical):
                parsed.indent_errors.append((group[0][0], logical))

        if first.startswith("\t"):
            parsed.statements.append(Statement(group[0][0], "recipe", logical))
            prev_rule = True
            continue

        assignment = ASSIGN_RE.match(logical)
        if assignment:
            parsed.statements.append(
                Statement(
                    group[0][0],
                    "assign",
                    logical,
                    name=assignment.group(1),
                    op=assignment.group(2),
                    value=assignment.group(3).strip(),
                )
            )
            prev_rule = False
            continue

        include = INCLUDE_RE.match(logical)
        if include:
            parsed.statements.append(Statement(group[0][0], "include", include.group(1).strip()))
            prev_rule = False
            continue

        parsed.statements.append(Statement(group[0][0], "other", logical))
        prev_rule = looks_like_rule(logical)
    return parsed


def include_kinds(statement: Statement) -> set[str]:
    """Map an include line onto the SDP makefile names it pulls in."""

    if statement.kind != "include":
        return set()
    text = statement.text
    found: set[str] = set()
    if "qconfig.mk" in text or "$(QCONFIG)" in text or "${QCONFIG}" in text:
        found.add("qconfig.mk")
    if "qtargets.mk" in text:
        found.add("qtargets.mk")
    if "recurse.mk" in text or "$(QRECURSE)" in text or "${QRECURSE}" in text:
        found.add("recurse.mk")
    if "common.mk" in text:
        found.add("common.mk")
    return found
