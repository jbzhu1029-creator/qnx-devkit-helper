"""Environment checks against a fake filesystem. No real SDP is required."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qnxdoctor.environment import evaluate_environment
from qnxdoctor.sdp import describe_spec
from support import make_sdp8, snapshot, write


def ids(notes, severity: str | None = None) -> set[str]:
    return {note.check_id for note in notes if severity is None or note.severity == severity}


class EnvironmentTests(unittest.TestCase):
    def test_specs_do_not_confuse_x86_with_x86_64(self) -> None:
        self.assertEqual(describe_spec("gcc_ntox86_64")[0], "ok")
        self.assertEqual(describe_spec("gcc_ntox86_64_cxx")[0], "ok")
        self.assertEqual(describe_spec("gcc_ntoaarch64le")[0], "ok")
        self.assertEqual(describe_spec("gcc_ntox86"), ("legacy", describe_spec("gcc_ntox86")[1]))
        self.assertEqual(describe_spec("gcc_ntoarmv7le")[0], "legacy")
        self.assertIn("gcc_ntoaarch64le", describe_spec("gcc_ntoaarch64")[1])

    def test_inactive_shell_is_degraded_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            notes = evaluate_environment(snapshot({}, home))
        self.assertEqual(ids(notes, "error"), set())
        self.assertTrue(
            {
                "env.qnx-host-unset",
                "env.qnx-target-unset",
                "env.qcc-missing",
                "env.qxx-missing",
                "env.makeflags-missing",
                "env.mk-includes-unverified",
                "env.sdp-not-found",
            }
            <= ids(notes, "warning")
        )
        self.assertIn("env.mk-not-required", ids(notes, "info"))
        self.assertIn("env.make", ids(notes, "ok"))

    def test_ready_fake_sdp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "qnx800"
            env = make_sdp8(root)
            host_bin = Path(env["QNX_HOST"]) / "usr" / "bin"
            notes = evaluate_environment(
                snapshot(
                    env,
                    Path(env["HOME"]),
                    tools={
                        "qcc": str(host_bin / "qcc"),
                        "q++": str(host_bin / "q++"),
                        "make": "/usr/bin/make",
                    },
                    qcc_dash_v="gcc_ntoaarch64le\ngcc_ntox86_64\n",
                )
            )
        self.assertEqual(ids(notes, "error"), set())
        self.assertEqual(ids(notes, "warning"), set())
        self.assertTrue(
            {"env.qnx-host", "env.qnx-target", "env.qcc", "env.qxx", "env.makeflags", "env.mk-includes", "env.qcc-specs"}
            <= ids(notes, "ok")
        )

    def test_qnx_host_pointing_at_the_sdp_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "qnx800"
            env = make_sdp8(root)
            env["QNX_HOST"] = str(root)
            notes = evaluate_environment(snapshot(env, Path(env["HOME"]), tools={"qcc": None, "q++": None}))
        self.assertIn("env.qnx-host-is-base", ids(notes, "error"))

    def test_sdp7_target_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            target = base / "qnx710" / "target" / "qnx7"
            include = target / "usr" / "include"
            (include / "mk").mkdir(parents=True)
            (include / "qconfig.mk").write_text("\n")
            (include / "mk" / "qtargets.mk").write_text("\n")
            (include / "mk" / "recurse.mk").write_text("\n")
            host = base / "qnx710" / "host" / "linux" / "x86_64"
            (host / "usr" / "bin").mkdir(parents=True)
            (host / "usr" / "bin" / "qcc").write_text("\n")
            env = {
                "QNX_HOST": str(host),
                "QNX_TARGET": str(target),
                "PATH": str(host / "usr" / "bin"),
                "MAKEFLAGS": f"-I{include}",
            }
            notes = evaluate_environment(
                snapshot(env, base, tools={"qcc": str(host / "usr" / "bin" / "qcc"), "q++": None})
            )
        self.assertIn("env.sdp-wrong-version", ids(notes, "error"))

    def test_makeflags_must_include_the_target_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "qnx800"
            env = make_sdp8(root)
            env["MAKEFLAGS"] = "-j4"
            host_bin = Path(env["QNX_HOST"]) / "usr" / "bin"
            notes = evaluate_environment(
                snapshot(
                    env,
                    Path(env["HOME"]),
                    tools={"qcc": str(host_bin / "qcc"), "q++": str(host_bin / "q++")},
                )
            )
        matched = [note for note in notes if note.check_id == "env.makeflags-missing"]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].severity, "error")

    def test_host_include_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            notes = evaluate_environment(snapshot({"CPATH": "/usr/include", "LIBRARY_PATH": "/usr/lib"}, home))
        self.assertIn("env.host-include-leak", ids(notes, "error"))
        self.assertIn("env.host-lib-leak", ids(notes, "error"))

    def test_macos_host_is_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            notes = evaluate_environment(snapshot({}, Path(tmp), system="Darwin", machine="arm64"))
        self.assertIn("env.host-unsupported", ids(notes, "warning"))

    def test_installed_but_not_sourced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            root = home / "qnx800"
            root.mkdir()
            (root / "qnxsdp-env.sh").write_text("# QNX Software Development Platform 8.0\n")
            (root / "host").mkdir()
            notes = evaluate_environment(snapshot({}, home, roots=(root,)))
        self.assertIn("env.sdp-installed-not-sourced", ids(notes, "warning"))
        self.assertNotIn("env.sdp-not-found", ids(notes))
        matched = [note for note in notes if note.check_id == "env.sdp-installed-not-sourced"]
        self.assertIn("~/qnx800", matched[0].message)

    def test_only_sdp7_is_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            root = home / "qnx710"
            root.mkdir()
            (root / "qnxsdp-env.sh").write_text("# QNX Software Development Platform 7.1\n")
            notes = evaluate_environment(snapshot({}, home, roots=(root,)))
        self.assertIn("env.sdp-wrong-version", ids(notes, "warning"))

    def test_qcc_shadowed_by_another_binary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "qnx800"
            env = make_sdp8(root)
            other = write(Path(tmp), "decoy/qcc", "#!/bin/sh\n", executable=True)
            host_qcc = str(Path(env["QNX_HOST"]) / "usr" / "bin" / "qcc")
            notes = evaluate_environment(
                snapshot(env, Path(env["HOME"]), tools={"qcc": str(other), "q++": None})
            )
            self.assertNotEqual(host_qcc, str(other))
        self.assertIn("env.qcc-shadowed", ids(notes, "error"))


if __name__ == "__main__":
    unittest.main()
