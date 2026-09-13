"""Static guardrails complement the real native active-process smoke."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ShutdownUIGuardrails(unittest.TestCase):
    def test_main_window_remains_owned_and_visible_until_shutdown_reply(self):
        source = (ROOT / "macos/IntegraApp.swift").read_text()
        self.assertIn("window.isReleasedWhenClosed = false", source)
        self.assertIn("window.delegate = self", source)
        handler = source.split("func windowShouldClose(_", 1)[1].split("func applicationShouldTerminate(_", 1)[0]
        self.assertIn("NSApp.terminate(nil)", handler)
        self.assertIn("return false", handler)

    def test_native_waits_for_verified_service_reply(self):
        source = (ROOT / "macos/IntegraApp.swift").read_text()
        handler = source.split("func applicationShouldTerminate(_", 1)[1].split("func applicationWillTerminate", 1)[0]
        self.assertIn("return .terminateLater", handler)
        self.assertNotIn(".terminateNow", handler)
        self.assertIn('service.json("shutdown-active-runs")', handler)
        self.assertIn('"SHUTDOWN_READY"', handler)
        self.assertIn("serviceQueue.async", handler)
        self.assertIn("RunLoop.main.perform(inModes: [.default, .modalPanel, .eventTracking])", handler)
        self.assertIn("MainActor.assumeIsolated", handler)
        self.assertIn("reply(toApplicationShouldTerminate: false)", handler)
        self.assertIn("self.window.makeKeyAndOrderFront(nil)", handler)

    def test_new_starts_are_gated_and_pending_calls_drain_before_shutdown(self):
        source = (ROOT / "macos/IntegraApp.swift").read_text()
        self.assertNotIn("DispatchQueue.global", source)
        self.assertIn('DispatchQueue(label: "Integra.native-services"', source)
        for action in ("execute", "retryRun"):
            self.assertIn(f"func {action}() {{\n    guard !terminationPending else {{ return }}", source)
        self.assertIn("window.ignoresMouseEvents = true", source)
        self.assertIn("self.window.ignoresMouseEvents = false", source)

    def test_all_terminating_build_probes_have_isolated_data(self):
        script = (ROOT / "scripts/test_macos_app.sh").read_text()
        for line in script.splitlines():
            if line.startswith(("INTEGRA_LAUNCH_PROBE=", "INTEGRA_CLOSE_PROBE=")):
                self.fail("Native shutdown probes must not use real user application data")
        self.assertIn('INTEGRA_APP_DATA_ROOT="$test_root/app-data" INTEGRA_LAUNCH_PROBE=', script)
        self.assertIn('INTEGRA_APP_DATA_ROOT="$test_root/app-data" INTEGRA_CLOSE_PROBE=', script)
        self.assertIn("native_shutdown_probe.py", script)
