"""Project-file checks. These are the cases CI can run with no QNX SDP."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qnxdoctor.project import diagnose_project

REPO = Path(__file__).resolve().parents[1]


def by_severity(notes, severity: str) -> list[str]:
    return sorted(note.check_id for note in notes if note.severity == severity)


class ExampleProjectTests(unittest.TestCase):
    def test_hello_sdp8_has_no_project_problems(self) -> None:
        result = diagnose_project(REPO / "examples" / "hello-sdp8")
        self.assertEqual(result.style, "qnx-mk")
        self.assertEqual(by_severity(result.notes, "error"), [])
        self.assertEqual(by_severity(result.notes, "warning"), [])
        self.assertIn("variant.targets", by_severity(result.notes, "ok"))
        self.assertIn("mk.qtargets-included", by_severity(result.notes, "ok"))

    def test_plain_aarch64_has_no_project_problems(self) -> None:
        result = diagnose_project(REPO / "examples" / "plain-aarch64")
        self.assertEqual(result.style, "plain")
        self.assertEqual(by_severity(result.notes, "error"), [])
        self.assertEqual(by_severity(result.notes, "warning"), [])
        self.assertIn("plain.target-spec", by_severity(result.notes, "ok"))

    def test_variant_directory_lifts_to_the_project_root(self) -> None:
        result = diagnose_project(REPO / "examples" / "hello-sdp8" / "nto-aarch64-o-le")
        self.assertEqual(result.root.name, "hello-sdp8")
        self.assertEqual(by_severity(result.notes, "error"), [])

    def test_broken_port_reports_the_known_mistakes(self) -> None:
        result = diagnose_project(REPO / "examples" / "broken-port")
        self.assertEqual(
            by_severity(result.notes, "error"),
            sorted(
                [
                    "mk.qtargets-missing",
                    "project.host-compiler",
                    "project.legacy-sdp-path",
                    "project.march-native",
                    "source.linux-header",
                    "variant.big-endian",
                    "variant.cpu-unsupported",
                ]
            ),
        )
        self.assertEqual(
            by_severity(result.notes, "warning"),
            sorted(
                [
                    "link.libc-builtins",
                    "link.socket-missing",
                    "mk.list-incomplete",
                    "script.sdk-env-not-sourced",
                    "script.sdk-env-not-sourced",
                    "source.epoll",
                ]
            ),
        )


class SyntheticProjectTests(unittest.TestCase):
    def test_host_make_is_not_a_qnx_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Makefile").write_text("CC = gcc\nall: hello\n")
            result = diagnose_project(root)
        self.assertEqual(by_severity(result.notes, "error"), ["project.not-qnx"])

    def test_commented_host_compiler_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Makefile").write_text(
                "# CC = gcc\nCC = qcc\nTARGET_ARCH = -Vgcc_ntoaarch64le\n"
            )
            (root / "hello.c").write_text("int main(void){return 0;}\n")
            result = diagnose_project(root)
        self.assertEqual(by_severity(result.notes, "error"), [])
        self.assertNotIn("project.host-compiler", by_severity(result.notes, "warning"))

    def test_define_block_does_not_set_the_compiler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Makefile").write_text(
                "define HELP\nCC = gcc\nendef\nCC = qcc\nTARGET_ARCH = -Vgcc_ntox86_64\n"
            )
            result = diagnose_project(root)
        self.assertNotIn("project.host-compiler", by_severity(result.notes, "error"))
        self.assertNotIn("project.bad-spec", by_severity(result.notes, "error"))
        self.assertIn("plain.target-spec", by_severity(result.notes, "ok"))

    def test_plain_qcc_without_a_spec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Makefile").write_text("CC = qcc\nall: hello\n\t$(CC) hello.c -o hello\n")
            result = diagnose_project(root)
        self.assertIn("plain.missing-target-spec", by_severity(result.notes, "error"))

    def test_legacy_spec_is_not_treated_as_x86_64(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Makefile").write_text("CC = qcc\nTARGET_ARCH = -Vgcc_ntox86\n")
            result = diagnose_project(root)
        self.assertIn("project.bad-spec", by_severity(result.notes, "error"))
        self.assertNotIn("plain.missing-target-spec", by_severity(result.notes, "error"))

    def test_recipe_indented_with_spaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Makefile").write_text(
                "CC = qcc\nTARGET_ARCH = -Vgcc_ntoaarch64le\nall: hello\n    $(CC) $(TARGET_ARCH) hello.c -o hello\n"
            )
            result = diagnose_project(root)
        self.assertIn("make.recipe-spaces", by_severity(result.notes, "error"))

    def test_socket_library_satisfies_the_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Makefile").write_text(
                "CC = qcc\nTARGET_ARCH = -Vgcc_ntoaarch64le\nLDLIBS += -lsocket\n"
            )
            (root / "net.c").write_text("int main(void){return socket(0,0,0);}\n")
            result = diagnose_project(root)
        self.assertIn("link.socket", by_severity(result.notes, "ok"))
        self.assertNotIn("link.socket-missing", by_severity(result.notes, "warning"))

    def test_qnx_ifdef_downgrades_a_linux_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Makefile").write_text("CC = qcc\nTARGET_ARCH = -Vgcc_ntoaarch64le\n")
            (root / "port.c").write_text(
                "#ifdef __QNXNTO__\n#include <stdio.h>\n#else\n#include <linux/if.h>\n#endif\n"
            )
            result = diagnose_project(root)
        linux = [note for note in result.notes if note.check_id == "source.linux-header"]
        self.assertEqual(len(linux), 1)
        self.assertEqual(linux[0].severity, "info")

    def test_preset_macros_after_qtargets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "common.mk").write_text(
                "include $(QCONFIG)\ninclude $(MKFILES_ROOT)/qtargets.mk\nNAME=hello\n"
            )
            (root / "Makefile").write_text("LIST=OS CPU VARIANT\ninclude $(QRECURSE)\n")
            variant = root / "nto-x86_64-o"
            variant.mkdir()
            (variant / "Makefile").write_text("include ../common.mk\n")
            result = diagnose_project(root)
        self.assertIn("mk.preset-after-qtargets", by_severity(result.notes, "warning"))

    def test_variant_makefile_must_include_common(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "common.mk").write_text(
                "include $(QCONFIG)\nNAME=hello\ninclude $(MKFILES_ROOT)/qtargets.mk\n"
            )
            (root / "Makefile").write_text("LIST=OS CPU VARIANT\ninclude $(QRECURSE)\n")
            variant = root / "nto-aarch64-o-le"
            variant.mkdir()
            (variant / "Makefile").write_text("all:\n\t@echo missing common\n")
            result = diagnose_project(root)
        self.assertIn("variant.missing-common", by_severity(result.notes, "error"))

    def test_sourced_script_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Makefile").write_text("CC = qcc\nTARGET_ARCH = -Vgcc_ntoaarch64le\n")
            (root / "build.sh").write_text("#!/bin/sh\n. \"$HOME/qnx800/qnxsdp-env.sh\"\nmake\n")
            result = diagnose_project(root)
        self.assertNotIn("script.sdk-env-not-sourced", by_severity(result.notes, "warning"))


if __name__ == "__main__":
    unittest.main()
