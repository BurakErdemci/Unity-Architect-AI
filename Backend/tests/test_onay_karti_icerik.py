"""K9 — onay kartı kullanıcıya NE onayladığını gösteriyor mu?

Kusur: SDK yolundaki kart `Write → yol` yazıyordu, yazılacak içeriği HİÇ
göstermiyordu. Aynı üründe kardeş yol bunu doğru yapıyordu — unityMCP
köprüsünün `write_file`'ı ya tam içeriği ya diff'i çiziyor. Yani kullanıcı,
isteğin hangi kanaldan geldiğine bağlı olarak ya gördüğünü ya görmediğini
onaylıyordu.

Ölçüt "fonksiyon çağrıldı" DEĞİL "metin kartta görünüyor": testler kartın
gerçekten taşıyacağı dizeyi üretip içinde arıyor.

İKİ ÇAĞIRAN VAR ve ayrımı korumak testlerin işi:
  • onay kartı → `tam_govde=True`, içerik görünür
  • sohbet çipi → varsayılan, içerik GİTMEZ (çip zaten kırpılıyor; gövdeyi
    göndermek ekranda hiçbir şey kazandırmadan SSE akışını şişirir)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

GOVDE = "public class Zararli { void Sil() { Directory.Delete(yol, true); } }"


class TestYazmaKartiIcerigiGosteriyor(unittest.TestCase):
    """Onay kartı yolu — kullanıcının karar verdiği yer."""

    def test_Write_yazilacak_icerigi_gosteriyor(self):
        from providers.claude_sdk_session import _describe_tool
        metin = _describe_tool("Write", {"file_path": "Assets/A.cs", "content": GOVDE},
                               tam_govde=True)
        self.assertIn("Assets/A.cs", metin, "yol kaybolmuş")
        self.assertIn(GOVDE, metin, "içerik gösterilmiyor — kullanıcı görmediğini onaylar")

    def test_Edit_ESKI_ve_YENI_dizeyi_birlikte_gosteriyor(self):
        """Kararı değiştiren şey tam olarak bu iki dize; biri eksikse
        kullanıcı değişikliğin yönünü göremez."""
        from providers.claude_sdk_session import _describe_tool
        metin = _describe_tool("Edit", {"file_path": "A.cs",
                                        "old_string": "hiz = 1;",
                                        "new_string": "hiz = 999;"},
                               tam_govde=True)
        self.assertIn("hiz = 1;", metin)
        self.assertIn("hiz = 999;", metin)

    def test_MultiEdit_HER_duzenlemeyi_gosteriyor(self):
        """Tek onay bütün paketi yetkilendiriyor → paketin tamamı görünmeli.

        Aynı sınıf köprü tarafında bir denetim bulgusuydu: `batch_execute`'ta
        ikinci sıradaki SİLME kartta hiç görünmüyor ama onay onu da kapsıyordu.
        """
        from providers.claude_sdk_session import _describe_tool
        metin = _describe_tool("MultiEdit", {"file_path": "A.cs", "edits": [
            {"old_string": "zararsiz_bir", "new_string": "degisiklik"},
            {"old_string": "kritik_kontrol", "new_string": ""},
        ]}, tam_govde=True)
        self.assertIn("zararsiz_bir", metin)
        self.assertIn("kritik_kontrol", metin, "ikinci düzenleme kartta görünmüyor")

    def test_uzun_icerik_kirpiliyor_ama_GIZLENEN_SAYISI_yaziliyor(self):
        """Sessiz kırpma kırpmanın kendisinden tehlikeli: kullanıcı 'burada
        dahası var mı' sorusunu sorabilmeli."""
        from providers.claude_sdk_session import _describe_tool, _KART_DEGER_SINIRI
        uzun = "A" * (_KART_DEGER_SINIRI + 137)
        metin = _describe_tool("Write", {"file_path": "A.cs", "content": uzun},
                               tam_govde=True)
        self.assertLess(len(metin), len(uzun) + 200, "kırpma hiç uygulanmamış")
        self.assertIn("137 karakter gizlendi", metin)

    def test_bos_icerikli_yazim_kartta_YANILTMIYOR(self):
        """Boş dosya yazımında gövde yok; kart yine de yolu söylemeli."""
        from providers.claude_sdk_session import _describe_tool
        metin = _describe_tool("Write", {"file_path": "A.cs", "content": ""},
                               tam_govde=True)
        self.assertIn("A.cs", metin)

    def test_bozuk_yuk_karti_DUSURMUYOR(self):
        """Şekli beklenmedik bir yük istisna atarsa kart hiç çizilmez ve istek
        sessizce ölür — kartsız kalmak her durumda daha kötü (aynı sınıf
        31 Tem 2026'da frontend tarafında gerçekten yaşandı)."""
        from providers.claude_sdk_session import _describe_tool
        for yuk in ({"file_path": "A.cs", "edits": "liste değil"},
                    {"file_path": "A.cs", "content": 12345},
                    {}):
            with self.subTest(yuk=yuk):
                self.assertIsInstance(_describe_tool("MultiEdit", yuk, tam_govde=True), str)
                self.assertIsInstance(_describe_tool("Write", yuk, tam_govde=True), str)


class TestCipGovdeTasimiyor(unittest.TestCase):
    """Çip yolu — burada karar YOK, dolayısıyla gövde de yok.

    Bu sınıf bir gerilemeyi kolluyor: K9 düzeltmesi `_describe_tool`'u tek
    çağıranı varmış gibi değiştirseydi, dosya içerikleri her araç çağrısında
    SSE akışına girerdi. `_trim_args`'ın argümanları 1200'de kesmesi tam olarak
    bu maliyeti önlemek için konmuştu.
    """

    def test_cip_ozeti_dosya_icerigini_TASIMIYOR(self):
        from providers.claude_sdk_session import _describe_tool
        ozet = _describe_tool("Write", {"file_path": "Assets/A.cs", "content": GOVDE})
        self.assertIn("Assets/A.cs", ozet)
        self.assertNotIn(GOVDE, ozet, "çip gövdeyi taşıyor — SSE gereksiz şişer")

    def test_ONAY_KARTI_cagrisi_tam_govde_ISTIYOR(self):
        """Kaynak düzeyinde nöbetçi: kartı üreten çağrıdan bayrak düşemesin.

        Yukarıdaki testler fonksiyonu DOĞRUDAN çağırıyor, yani çağrı yerindeki
        `tam_govde=True` silinse hepsi yeşil kalır ve kart sessizce eski
        (içeriksiz) hâline döner — kusur tam olarak orada yaşıyordu.
        """
        yol = os.path.join(os.path.dirname(__file__), "..", "app",
                           "providers", "claude_sdk_session.py")
        with open(yol, encoding="utf-8") as f:
            satirlar = f.read().splitlines()
        kart_satirlari = [s for s in satirlar if '"command": _describe_tool' in s]
        self.assertTrue(kart_satirlari, "onay kartı çağrısı bulunamadı — test bayatlamış")
        for satir in kart_satirlari:
            self.assertIn("tam_govde=True", satir,
                          f"onay kartı gövdesiz üretiliyor: {satir.strip()}")

    def test_Bash_davranisi_DEGISMEDI(self):
        """Komut yolu zaten doğruydu; K9 düzeltmesi onu iki kipte de bozmamalı."""
        from providers.claude_sdk_session import _describe_tool
        self.assertEqual(_describe_tool("Bash", {"command": "git status"}), "git status")
        self.assertEqual(_describe_tool("Bash", {"command": "git status"}, tam_govde=True),
                         "git status")


if __name__ == "__main__":
    unittest.main()
