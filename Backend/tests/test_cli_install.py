"""Windows/macOS görünür CLI kurulum ve giriş akışı regresyon testleri."""
import asyncio
import os
import shutil
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from routes.config_routes import (
    _MAC_INSTALL_CMDS,
    _MAC_LOGIN_CMDS,
    create_config_router,
    _install_terminal_command,
    _open_visible_terminal,
)


class TestInstallCommands(unittest.TestCase):
    def test_every_cli_has_a_mac_installer(self):
        self.assertEqual(
            set(_MAC_INSTALL_CMDS),
            {"claude", "codex", "agy", "cursor", "copilot", "opencode"},
        )

    def test_every_mac_install_continues_to_its_interactive_login(self):
        # zsh yolu SABİT YAZILMAZ. `/bin/zsh` macOS'ta var ama ubuntu runner'da
        # yok ve bu test orada altı subtest'in altısını birden düşürüyordu
        # (`FileNotFoundError`, ölçüldü CI 2026-07-28) — yani macOS'ta yeşil
        # olan bir test Linux'ta ürünle ilgisiz bir sebeple kırmızıydı.
        # Metin iddiaları her platformda koşmaya devam ediyor; koşulsuz olan
        # yalnız sözdizimi kapısı, ve zsh kurulu olan her yerde o da koşuyor
        # (CI iş akışı zsh kuruyor, bkz .github/workflows/test.yml).
        zsh = shutil.which("zsh")
        for cli, (install_cmd, needs_npm) in _MAC_INSTALL_CMDS.items():
            with self.subTest(cli=cli):
                command = _install_terminal_command(cli, install_cmd, needs_npm, "darwin")
                self.assertIn(install_cmd, command)
                self.assertIn(_MAC_LOGIN_CMDS[cli], command)
                self.assertIn("install_status", command)
                if zsh is None:
                    self.skipTest("zsh bulunamadı — sözdizimi kapısı atlandı, metin iddiaları koştu")
                parsed = subprocess.run(
                    [zsh, "-n", "-c", command],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(parsed.returncode, 0, parsed.stderr)

    @patch("routes.config_routes.subprocess.run")
    def test_mac_terminal_uses_launch_services_command_file(self, run_mock):
        run_mock.return_value = MagicMock(returncode=0, stdout="", stderr="")

        _open_visible_terminal("echo test", platform="darwin")

        argv = run_mock.call_args.args[0]
        self.assertEqual(argv[:3], ["/usr/bin/open", "-a", "Terminal"])
        script_path = argv[3]
        try:
            with open(script_path, "r", encoding="utf-8") as handle:
                script = handle.read()
            self.assertIn("echo test", script)
            self.assertIn(".zshrc", script)
        finally:
            os.unlink(script_path)

    @patch("routes.config_routes.subprocess.Popen")
    def test_windows_terminal_behavior_is_preserved(self, popen_mock):
        _open_visible_terminal("Write-Host test", platform="win32")

        argv = popen_mock.call_args.args[0]
        self.assertEqual(argv[0], "powershell")
        self.assertIn("-NoExit", argv)


class TestCliModelPlanCaps(unittest.TestCase):
    def test_codex_models_are_never_disabled_by_stale_plan_caps(self):
        router = create_config_router(MagicMock())
        endpoint = next(
            route.endpoint
            for route in router.routes
            if getattr(route, "path", "") == "/cli-models/{cli}"
        )

        with patch("routes.config_routes._resolve_general_cli", return_value="/fake/codex"), \
             patch("providers.oneshot_cli.get_named_models_cap", return_value=False):
            result = asyncio.run(endpoint(cli="codex", x_session_token=""))

        sol = next(model for model in result["models"] if model["id"] == "gpt-5.6-sol")
        self.assertNotIn("disabled", sol)
        self.assertNotIn("disabled_reason", sol)


if __name__ == "__main__":
    unittest.main()
