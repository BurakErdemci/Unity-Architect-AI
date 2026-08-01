"""K5(a) — prompt KALICI loglara sızmıyor mu?

ÖLÇÜLMÜŞ ZİNCİR (2026-08-01, uçtan uca):
    cli_base `[CMD]` satırı → backend stdout → Electron `console.log`
    → `fileLog` → `%TEMP%/unity-architect-ai.log` (`fs.appendFileSync`)
Yani `[CMD]` uçucu bir konsol satırı DEĞİL; kullanıcının sohbete yapıştırdığı
her şey (kod, dosya yolu, elle girilmiş bir anahtar) diske birikiyordu.

Bu testlerin ölçtüğü şey maskenin KENDİSİ değil, ÜRÜNÜN GERÇEK argv'leri:
her sağlayıcının kendi `_build_cmd`'i çağrılıyor. Sebebi K3'ten ders: bir
muhafızı sahte bir girdiyle sınamak, ürünün o girdiyi hiç üretmediği durumu
göremiyor. Her testte önce POZİTİF KONTROL var — canary ham argv'de gerçekten
görünüyor mu; görünmüyorsa test bir şey ölçmüyordur ve kırmızı verir.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

# Ürünün loglayacağı metinde ARANACAK olan iğne. Gerçek bir sır değil; bir
# kullanıcının sohbete yapıştırabileceği türden ayırt edici bir dize.
CANARY = "GIZLI-PROMPT-ICERIGI-4f3a9c"


def _mock_unity_mcp(running=False):
    m = MagicMock()
    m.unity_mcp_manager.is_running.return_value = running
    m.unity_mcp_manager.mcp_port = 8080
    return patch.dict(sys.modules, {"unity_ai_mcp": MagicMock(unity_mcp_manager=m.unity_mcp_manager),
                                    "unity_ai_mcp.unity_mcp_manager": m})


def _tum_saglayici_cmdleri(prompt: str):
    """Beş sağlayıcının GERÇEK argv'sini üretir → [(ad, cmd), ...]

    agy bilerek YOK: onun prompt'u `cmd`'ye hiç girmiyor, spawn anında ayrı
    argüman olarak veriliyor (cli_base `agy_prompt`), yani `[CMD]` satırından
    zaten görünmüyor. Buraya eklemek testi sahte-yeşil yapardı.
    """
    from providers.claude_provider import ClaudeCodeProvider
    from providers.codex_provider import CodexProvider
    from providers.cursor_provider import CursorProvider
    from providers.copilot_provider import CopilotProvider
    from providers.opencode_provider import OpenCodeProvider

    with _mock_unity_mcp(), \
            patch("providers.cursor_provider.resolve_cursor_cmd", return_value=["agent"]), \
            patch("providers.copilot_provider.resolve_copilot_cmd", return_value=["copilot"]), \
            patch("providers.opencode_provider.resolve_opencode_cmd", return_value=["opencode"]):
        return [
            ("claude", ClaudeCodeProvider(binary_name="claude-opus-5")._build_cmd(prompt)),
            ("codex", CodexProvider(binary_name="gpt-5.5")._build_cmd(prompt)),
            ("cursor", CursorProvider(binary_name="cursor-composer-2.5")._build_cmd(prompt)),
            ("copilot", CopilotProvider(binary_name="copilot-claude-sonnet-5")._build_cmd(prompt)),
            ("opencode", OpenCodeProvider(binary_name="opencode:opencode/big-pickle")._build_cmd(prompt)),
        ]


class TestPromptLogaGirmiyor(unittest.TestCase):

    def test_hicbir_saglayicinin_CMD_satiri_prompt_ICERMIYOR(self):
        from providers.cli_base import maskeli_cmd
        for ad, cmd in _tum_saglayici_cmdleri(CANARY):
            with self.subTest(saglayici=ad):
                ham = " ".join(str(p) for p in cmd)
                # POZİTİF KONTROL: sızıntı yüzeyi gerçekten var mı?
                self.assertIn(CANARY, ham,
                              f"{ad}: prompt ham argv'de yok — test bir şey ölçmüyor")
                self.assertNotIn(CANARY, maskeli_cmd(cmd, CANARY),
                                 f"{ad}: prompt maskelenmiş [CMD] satırında HÂLÂ görünüyor")

    def test_maske_her_seyi_yemiyor__komut_teshis_edilebilir_kaliyor(self):
        """Maske sızıntıyı kapatırken log'u işe yaramaz hale getirmemeli.

        Bu testin sebebi: "hepsini maskele" de sızıntıyı kapatır ama teşhis
        yeteneğini sıfırlar; o zaman kimse fark etmeden log tamamen ölür.
        """
        from providers.cli_base import maskeli_cmd
        for ad, cmd in _tum_saglayici_cmdleri(CANARY):
            with self.subTest(saglayici=ad):
                maskeli = maskeli_cmd(cmd, CANARY)
                self.assertIn(str(cmd[0]), maskeli, f"{ad}: ikili adı bile kaybolmuş")
                self.assertIn("<prompt:", maskeli, f"{ad}: maske hiç uygulanmamış")

    def test_prompt_bir_HINT_metnine_yapisiksa_da_maskeleniyor(self):
        """Üç sağlayıcı prompt'u statik bir hint'in SONUNA yapıştırıyor.

        Yani maskelenmesi gereken öğe prompt'a EŞİT değil, onu İÇERİYOR.
        Eşitlik ölçütü kullanan bir maske burada sessizce açılırdı.
        """
        from providers.cli_base import maskeli_cmd
        cmd = ["opencode", "run", "IMPORTANT — follow exactly:\n" + CANARY]
        self.assertNotIn(CANARY, maskeli_cmd(cmd, CANARY))

    def test_bos_prompt_her_seyi_maskelemiyor(self):
        """Boş dize her metnin alt dizesidir → naif bir maske komutu komple yerdi."""
        from providers.cli_base import maskeli_cmd
        self.assertEqual(maskeli_cmd(["claude", "--model", "opus"], ""),
                         "claude --model opus")

    def test_CMD_log_satiri_maskeden_GECIYOR(self):
        """Kaynak düzeyinde nöbetçi: `[CMD]` satırı ham `' '.join(cmd)`'ye geri dönmesin.

        Yukarıdaki testler maskeyi ölçüyor ama maskeyi ÇAĞIRAN satırı değil.
        Çağrı silinirse hepsi yeşil kalırdı — kusur tam olarak orada yaşıyordu.
        """
        yol = os.path.join(os.path.dirname(__file__), "..", "app", "providers", "cli_base.py")
        with open(yol, encoding="utf-8") as f:
            kaynak = f.read()
        # Ölçüt "[CMD] geçen satır" DEĞİL "[CMD] BASAN satır": ilki yorumları ve
        # docstring'leri de yakalıyordu (bu dosyanın kendi açıklaması dahil).
        cmd_satirlari = [s for s in kaynak.splitlines()
                         if "[CMD]" in s and "logger." in s]
        self.assertTrue(cmd_satirlari, "[CMD] log satırı bulunamadı — test bayatlamış")
        for satir in cmd_satirlari:
            self.assertIn("maskeli_cmd", satir,
                          f"[CMD] satırı maskeden geçmiyor: {satir.strip()}")


if __name__ == "__main__":
    unittest.main()
