"""Lexer tests. These lock comment, continuation, and recipe-tab behavior."""

from __future__ import annotations

import unittest
from pathlib import Path

from qnxdoctor.makeparse import include_kinds, parse_makefile


class MakeParseTests(unittest.TestCase):
    def test_comment_and_quotes(self) -> None:
        parsed = parse_makefile(
            Path("Makefile"),
            "CC = qcc # not gcc\nLIBS += socket # trailing\nNOTE = \"hash # stays\"\n",
        )
        variables = parsed.variables()
        self.assertEqual(variables["CC"], "qcc")
        self.assertEqual(variables["LIBS"], "socket")
        self.assertEqual(variables["NOTE"], '"hash # stays"')

    def test_continuation_joins_assignment(self) -> None:
        parsed = parse_makefile(Path("common.mk"), "LIBS += socket \\\n        m\n")
        self.assertEqual(parsed.variables()["LIBS"], "socket m")

    def test_define_body_is_not_an_assignment(self) -> None:
        parsed = parse_makefile(
            Path("common.mk"),
            "define HELP\nCC = gcc\nendef\nCC = qcc\n",
        )
        self.assertEqual(parsed.variables()["CC"], "qcc")
        self.assertIn("HELP", parsed.defines)

    def test_spaces_before_a_recipe_are_recorded(self) -> None:
        parsed = parse_makefile(
            Path("Makefile"),
            "all: hello\n    $(CC) hello.c -o hello\n",
        )
        self.assertEqual(len(parsed.indent_errors), 1)
        self.assertEqual(parsed.indent_errors[0][0], 2)

    def test_tabbed_recipe_is_clean(self) -> None:
        parsed = parse_makefile(
            Path("Makefile"),
            "all: hello\n\t$(CC) hello.c -o hello\n",
        )
        self.assertEqual(parsed.indent_errors, [])
        self.assertEqual(parsed.statements[-1].kind, "recipe")

    def test_crlf_and_qnx_includes(self) -> None:
        parsed = parse_makefile(
            Path("Makefile"),
            "include $(QCONFIG)\r\ninclude $(MKFILES_ROOT)/qtargets.mk\r\ninclude $(QRDIR)$(QRECURSE)\r\n",
        )
        kinds: set[str] = set()
        for statement in parsed.statements:
            kinds |= include_kinds(statement)
        self.assertEqual(kinds, {"qconfig.mk", "qtargets.mk", "recurse.mk"})


if __name__ == "__main__":
    unittest.main()
