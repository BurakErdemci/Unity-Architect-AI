"""K5 — prompt kalıcı loglara ve argv'ye sızmıyor mu?

İKİ AYRI MARUZİYET, iki ayrı yarım:

(a) KALICI LOG. Zincir 2026-08-01'de uçtan uca ölçüldü:
    cli_base `[CMD]` satırı → backend stdout → Electron `console.log`
    → `fileLog` → `%TEMP%/unity-architect-ai.log` (`fs.appendFileSync`).
    Yani `[CMD]` uçucu bir konsol satırı değildi; kullanıcının sohbete
    yapıştırdığı her şey diske birikiyordu. Çözüm: `maskeli_cmd`.

(b) ARGV. Prompt son pozisyonel argüman olduğu için makinedeki HER sürece
    görünüyordu (`ps` / `Get-CimInstance Win32_Process`). Çözüm: stdin kabulü
    CANLI ölçülen CLI'larda prompt stdin'e taşındı (`prompt_via_stdin`).

Testler ürünün GERÇEK argv'lerini üretiyor — her sağlayıcının kendi
`_build_cmd`'i çağrılıyor. Uydurma bir girdiyle sınanan muhafız, ürünün o
girdiyi hiç üretmediği durumu göremiyor (K3'ün dersi).
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

# Ürünün üreteceği metinde ARANACAK iğne. Gerçek bir sır değil; bir kullanıcının
# sohbete yapıştırabileceği türden ayırt edici bir dize.
CANARY = "GIZLI-PROMPT-ICERIGI-4f3a9c"

# Prompt'u stdin'den okuduğu CANLI ÖLÇÜLEN sağlayıcılar (2026-08-01).
STDIN_SAGLAYICILAR = {"claude", "codex", "copilot", "opencode"}

# ⛔ ADLANDIRILMIŞ İSTİSNALAR — prompt HÂLÂ argv'de.
#   cursor : CLI bu makinede kurulu değil → stdin kabulü ÖLÇÜLEMEDİ.
#   kimi   : abonelik yok ve CLI kurulu değil → ölçülemez.
#   agy    : ÖLÇÜLDÜ ve OLMUYOR — `agy --print` argümanı ZORUNLU kılıyor
#            ("flag needs an argument: -print"), yani yol yapısal olarak kapalı.
# Bu küme bilerek TESTE yazıldı: sessizce büyürse test kırılır.
ARGV_ISTISNALARI = {"cursor", "kimi", "agy"}


def _mock_unity_mcp(running=False):
    m = MagicMock()
    m.unity_mcp_manager.is_running.return_value = running
    m.unity_mcp_manager.mcp_port = 8080
    return patch.dict(sys.modules, {"unity_ai_mcp": MagicMock(unity_mcp_manager=m.unity_mcp_manager),
                                    "unity_ai_mcp.unity_mcp_manager": m})


def _saglayicilar(prompt: str):
    """Sağlayıcıların GERÇEK argv'lerini üretir → [(ad, provider, cmd), ...]

    agy burada yok: prompt'u `_build_cmd`'den geçmiyor, spawn anında ayrı
    argüman olarak veriliyor (cli_base `agy_prompt`). Ayrı testte ele alınıyor.
    """
    from providers.claude_provider import ClaudeCodeProvider
    from providers.codex_provider import CodexProvider
    from providers.cursor_provider import CursorProvider
    from providers.copilot_provider import CopilotProvider
    from providers.opencode_provider import OpenCodeProvider

    kurulanlar = [
        ("claude", ClaudeCodeProvider(binary_name="claude-opus-5")),
        ("codex", CodexProvider(binary_name="gpt-5.5")),
        ("cursor", CursorProvider(binary_name="cursor-composer-2.5")),
        ("copilot", CopilotProvider(binary_name="copilot-claude-sonnet-5")),
        ("opencode", OpenCodeProvider(binary_name="opencode:opencode/big-pickle")),
    ]
    with _mock_unity_mcp(), \
            patch("providers.cursor_provider.resolve_cursor_cmd", return_value=["agent"]), \
            patch("providers.copilot_provider.resolve_copilot_cmd", return_value=["copilot"]), \
            patch("providers.opencode_provider.resolve_opencode_cmd", return_value=["opencode"]):
        return [(ad, p, p._build_cmd(prompt)) for ad, p in kurulanlar]


class TestPromptArgvdeGorunmuyor(unittest.TestCase):
    """K5(b) — `ps` ile okunabilen komut satırında prompt var mı?"""

    def test_olculen_saglayicilarda_prompt_argvde_HIC_yok(self):
        for ad, p, cmd in _saglayicilar(CANARY):
            if ad not in STDIN_SAGLAYICILAR:
                continue
            with self.subTest(saglayici=ad):
                self.assertNotIn(CANARY, " ".join(str(x) for x in cmd),
                                 f"{ad}: prompt hâlâ argv'de — `ps` ile okunabilir")
                # POZİTİF KONTROL: prompt kaybolmadı, stdin yüküne geçti. Bu
                # olmadan "argv'de yok" testi, prompt'u tamamen düşüren bozuk
                # bir sağlayıcıda da yeşil kalırdı.
                self.assertIn(CANARY, p._stdin_payload or "",
                              f"{ad}: prompt argv'den çıkmış ama stdin yüküne de girmemiş")

    def test_istisnalar_ADLANDIRILMIS_ve_buyumemis(self):
        """Argv'de kalan sağlayıcı kümesi sessizce büyüyemez.

        Bir istisna gerekçesiz eklenirse bu test kırılır ve gerekçe yazılmaya
        zorlanır — K3'te aynı desen tek istisnayı görünür tutmuştu.
        """
        from providers.cli_base import BaseCLIProvider
        self.assertFalse(BaseCLIProvider.prompt_via_stdin,
                         "varsayılan argv OLMALI: stdin kabulü ölçülmeden varsayılamaz")
        for ad, p, _cmd in _saglayicilar("x"):
            with self.subTest(saglayici=ad):
                if ad in STDIN_SAGLAYICILAR:
                    self.assertTrue(p.prompt_via_stdin, f"{ad}: stdin'e taşınmış olmalıydı")
                else:
                    self.assertIn(ad, ARGV_ISTISNALARI,
                                  f"{ad}: argv'de kalıyor ama adlandırılmış istisna değil")


class TestPromptLogaGirmiyor(unittest.TestCase):
    """K5(a) — `[CMD]` satırı kalıcı log dosyasına ne yazıyor?"""

    def test_hicbir_saglayicinin_CMD_satiri_prompt_ICERMIYOR(self):
        from providers.cli_base import maskeli_cmd
        for ad, _p, cmd in _saglayicilar(CANARY):
            with self.subTest(saglayici=ad):
                self.assertNotIn(CANARY, maskeli_cmd(cmd, CANARY),
                                 f"{ad}: prompt [CMD] satırında görünüyor")

    def test_argvde_KALAN_saglayicida_maske_gercekten_calisiyor(self):
        """Maske testi boşa dönmesin: hâlâ argv kullanan bir sağlayıcıda önce
        sızıntının VAR olduğu, sonra maskenin kapattığı ölçülüyor."""
        from providers.cli_base import maskeli_cmd
        argvli = [(ad, cmd) for ad, _p, cmd in _saglayicilar(CANARY)
                  if ad not in STDIN_SAGLAYICILAR]
        self.assertTrue(argvli, "argv kullanan sağlayıcı kalmamış — test bayatladı")
        for ad, cmd in argvli:
            with self.subTest(saglayici=ad):
                ham = " ".join(str(x) for x in cmd)
                self.assertIn(CANARY, ham, f"{ad}: pozitif kontrol düştü")
                maskeli = maskeli_cmd(cmd, CANARY)
                self.assertNotIn(CANARY, maskeli)
                self.assertIn("<prompt:", maskeli)
                self.assertIn(str(cmd[0]), maskeli, f"{ad}: ikili adı bile kaybolmuş")

    def test_prompt_bir_HINT_metnine_yapisiksa_da_maskeleniyor(self):
        """Maskelenecek öğe prompt'a EŞİT değil, onu İÇERİYOR — eşitlik ölçütü
        kullanan bir maske burada sessizce açılırdı."""
        from providers.cli_base import maskeli_cmd
        cmd = ["opencode", "run", "IMPORTANT — follow exactly:\n" + CANARY]
        self.assertNotIn(CANARY, maskeli_cmd(cmd, CANARY))

    def test_bos_prompt_her_seyi_maskelemiyor(self):
        """Boş dize her metnin alt dizesidir → naif bir maske komutu komple yerdi."""
        from providers.cli_base import maskeli_cmd
        self.assertEqual(maskeli_cmd(["claude", "--model", "opus"], ""),
                         "claude --model opus")

    def test_CMD_log_satiri_maskeden_GECIYOR(self):
        """Kaynak düzeyinde nöbetçi: `[CMD]` satırı ham `' '.join(cmd)`'ye dönmesin.

        Diğer testler maskeyi ölçüyor ama maskeyi ÇAĞIRAN satırı değil; çağrı
        silinse hepsi yeşil kalırdı ve kusur tam orada yaşıyordu.
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
