"""Security invariants that do not need a live network.

The panel already has handler tests; these pin the architectural promises:
loopback only, no wildcard binds, portable process control, and a PID file
that is never trusted without checking the command line first.
"""

import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import webui

ROOT = Path(__file__).resolve().parents[1]
WEBUI = (ROOT / "webui.py").read_text(encoding="utf-8")
CORE = (ROOT / "mpv_ambilight.py").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
SECURITY = (ROOT / "SECURITY.md").read_text(encoding="utf-8")


class ListenerTests(unittest.TestCase):
    def test_panel_binds_only_loopback(self):
        self.assertIn('ThreadingHTTPServer(("127.0.0.1", port), handler)', WEBUI)
        self.assertNotIn("0.0.0.0", WEBUI)
        self.assertNotIn("0.0.0.0", CORE)

    def test_no_other_listening_socket(self):
        # The sync process sends UDP and never calls listen/accept.
        for source in (WEBUI, CORE):
            self.assertNotIn(".listen(", source)
            self.assertNotIn(".accept(", source)

    def test_csp_has_no_inline_code(self):
        self.assertIn("default-src 'none'", WEBUI)
        self.assertIn("script-src 'self'", WEBUI)
        self.assertNotIn("unsafe-inline", WEBUI)


class ProcessTests(unittest.TestCase):
    def test_killpg_is_optional(self):
        self.assertIn('getattr(os, "killpg", None)', WEBUI)
        self.assertNotIn("os.killpg(", WEBUI)
        self.assertIn("_stop_process_tree", WEBUI)

    def test_pid_is_not_trusted_without_a_cmdline(self):
        with mock.patch.object(webui, "_read_cmdline", return_value=""):
            self.assertFalse(webui._looks_like_ours(4242))
        with mock.patch.object(
            webui, "_read_cmdline", return_value=f"/usr/bin/python3 {webui.SCRIPT} --attach"
        ):
            self.assertTrue(webui._looks_like_ours(4242))

    def test_our_own_pid_is_never_adopted(self):
        self.assertFalse(webui._looks_like_ours(os.getpid()))

    def test_adopt_ignores_a_stale_pid_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("XDG_RUNTIME_DIR")
            os.environ["XDG_RUNTIME_DIR"] = tmp
            try:
                (Path(tmp) / "gui-daemon.json").write_text(
                    json.dumps({"pid": 4242, "started": 1.0, "mode": "attach"})
                )
                session = webui.Session(types.SimpleNamespace(port=0))
                with mock.patch.object(webui, "_pid_alive", return_value=True), mock.patch.object(
                    webui, "_looks_like_ours", return_value=False
                ):
                    session.adopt()
                self.assertIsNone(session.pid)
                self.assertFalse(session.adopted)
            finally:
                if old is None:
                    os.environ.pop("XDG_RUNTIME_DIR", None)
                else:
                    os.environ["XDG_RUNTIME_DIR"] = old


class CrazyTests(unittest.TestCase):
    def test_defaults_are_a_five_second_burst(self):
        self.assertEqual(webui.CRAZY_SECONDS, 5.0)
        self.assertEqual(webui.CRAZY_HZ, webui.CRAZY_MAX_HZ)

    def test_brightness_sweeps_from_ten_to_full_and_back(self):
        self.assertEqual(webui.crazy_frame(0.0, 5.0)["dimming"], 10)
        self.assertEqual(webui.crazy_frame(2.5, 5.0)["dimming"], 100)
        self.assertEqual(webui.crazy_frame(5.0, 5.0)["dimming"], 10)
        for step in range(11):
            frame = webui.crazy_frame(step * 0.5, 5.0)
            self.assertGreaterEqual(frame["dimming"], 10)
            self.assertLessEqual(frame["dimming"], 100)
            for channel in ("r", "g", "b"):
                self.assertGreaterEqual(frame[channel], 0)
                self.assertLessEqual(frame[channel], 255)


class DocumentationTests(unittest.TestCase):
    def test_architecture_diagram_is_committed(self):
        for name in ("architecture.mmd", "architecture.svg"):
            with self.subTest(name=name):
                path = ROOT / "docs" / name
                self.assertTrue(path.is_file(), f"docs/{name} is missing")
                self.assertGreater(path.stat().st_size, 500)
        self.assertIn("docs/architecture.svg", README)
        self.assertIn("architecture.svg", SECURITY)

    def test_ai_disclosure_is_accurate_for_this_repo(self):
        section = README.split("**How it was written.**", 1)[-1].split("## ", 1)[0]
        section = " ".join(section.split())
        self.assertIn("DeepSeek V4.1 Flash Free", section)
        self.assertIn("OpenCode", section)
        self.assertNotIn("Claude", section)
        self.assertNotIn("GPT-6", section)
        self.assertIn("not", section.lower())

    def test_security_doc_lists_the_exposed_interface(self):
        self.assertIn("127.0.0.1", SECURITY)
        self.assertIn("38899", SECURITY)


if __name__ == "__main__":
    unittest.main()
