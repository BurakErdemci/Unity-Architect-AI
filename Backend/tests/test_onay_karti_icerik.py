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

    def test_kart_gizlediginin_degil_YETKILENDIRDIGININ_tamamini_gosteriyor(self):
        """Denetim bulgusu `incomplete-approval-preview` (1 Ağu 2026).

        Kart 4000 karakterde kırpıyor ve "gizlendi" notu basıyordu; Onayla ise
        gövdenin TAMAMINI yetkilendiriyordu. 4000 zararsız karakterin ardına
        konan yıkıcı bir son ek kartta hiç görünmüyordu.

        ⛔ Sınırı büyütmek düzeltme değildi — eşik nereye konursa konsun
        "eşikten sonrasını gizle" sınıfı ayakta kalır ve saldırgan eşiği bilir.
        """
        from providers.claude_sdk_session import _describe_tool
        son_ek = "TEHLIKELI_SON_EK_HERSEYI_SIL"
        govde = "A" * 4100 + son_ek
        metin = _describe_tool("Write", {"file_path": "A.cs", "content": govde},
                               tam_govde=True)
        self.assertIn(son_ek, metin, "yetkilendirilen son ek kartta görünmüyor")

    def test_BOS_icerikli_yazim_sifir_bayta_indirdigini_SOYLUYOR(self):
        """Denetim bulgusu `ambiguous-destructive-approval` (1 Ağu 2026).

        `content=""` gövdesiz sayılıp yalnız `Write → yol` üretiyordu; yani var
        olan bir dosyayı sıfır bayta indiren işlem, içeriksiz bir özetten ayırt
        edilemiyordu. Silme etkisi olan bir işlem uyarısız onaylanıyordu.
        """
        from providers.claude_sdk_session import _describe_tool
        metin = _describe_tool("Write", {"file_path": "A.cs", "content": ""},
                               tam_govde=True)
        self.assertIn("A.cs", metin)
        # Metin doğrulama turundan sonra değişti: uyarı artık "gözle boş" ölçütünü
        # kullanıyor ve etkiyi ARACA GÖRE anlatıyor (bkz. TestDogrulamaTuruBulgulari).
        self.assertIn("GÖZLE BOŞ", metin, "boş yazımın etkisi kartta yazmıyor")
        # Ve çip özetinden AYIRT EDİLEBİLİR olmalı:
        self.assertNotEqual(metin, _describe_tool("Write", {"file_path": "A.cs", "content": ""}))

    def test_yazi_yonunu_ceviren_karakterler_HER_DALDA_etkisiz(self):
        """Denetim bulgusu `approval-visual-spoofing` (1 Ağu 2026).

        U+202E gibi karakterler tarayıcıda uygulanıyor → kartta okunan sıra,
        diske yazılacak sıradan farklı olabiliyordu. React ham HTML'i engelliyor
        ama bunlar HTML değil, metnin kendisi.

        Sınıf yalnız gövdede değildi: YOL, `Bash` komutu ve `WebFetch` adresi de
        modelin seçtiği metin. Bu yüzden kaçış dalların içinde değil ÇIKIŞTA
        yapılıyor ve bu test dört dalı birden kolluyor.
        """
        from providers.claude_sdk_session import _describe_tool
        RLO = "‮"
        vakalar = [
            ("Write", {"file_path": f"A{RLO}.cs", "content": "x"}),
            ("Bash", {"command": f"rm {RLO}txt.exe"}),
            ("WebFetch", {"url": f"http://a/{RLO}b"}),
            ("mcp__unityMCP__manage_scene", {"a": f"{RLO}x"}),
        ]
        for arac, yuk in vakalar:
            with self.subTest(arac=arac):
                self.assertNotIn(RLO, _describe_tool(arac, yuk, tam_govde=True))

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


class TestDogrulamaTuruBulgulari(unittest.TestCase):
    """Doğrulama turunun (1 Ağu 2026) kartta bulduğu beş kusur.

    Hepsi ilk düzeltmenin KENDİ getirdiği ya da kapatmadığı kardeş dallardı —
    yani "sınıfı kapattım" demenin, sınıfın öteki biçimlerini saymadan
    yapılamayacağının kanıtı.
    """

    def test_NotebookEdit_hedefi_ve_islemi_kartta_GORUNUYOR(self):
        """`notebook_approval_fields_omitted`: hedef `notebook_path`'te duruyordu,
        biz yalnız `file_path`/`path`'e bakıyorduk → kart `NotebookEdit → ?`
        yazıyor ve iki AYRI işlem birbirinin aynı kartını üretiyordu."""
        from providers.claude_sdk_session import _describe_tool
        guvenli = _describe_tool("NotebookEdit", {
            "notebook_path": "safe.ipynb", "cell_id": "cell-safe",
            "edit_mode": "replace", "new_source": "ayni kaynak"}, tam_govde=True)
        kritik = _describe_tool("NotebookEdit", {
            "notebook_path": "critical.ipynb", "cell_id": "cell-critical",
            "edit_mode": "delete", "new_source": "ayni kaynak"}, tam_govde=True)
        self.assertIn("safe.ipynb", guvenli)
        self.assertIn("cell-critical", kritik)
        self.assertIn("delete", kritik)
        self.assertNotEqual(guvenli, kritik, "iki ayrı işlem aynı kartı üretiyor")

    def test_SADECE_BOSLUK_iceren_yazim_da_uyariyor(self):
        """`whitespace_write_ambiguous`: uyarı Python doğruluk testine bağlıydı,
        yani yalnız `""`'i kapsıyordu; `"  \\t\\n "` kartta bomboş bir alan
        olarak çiziliyordu — aynı yıkıcı etki, uyarısız."""
        from providers.claude_sdk_session import _describe_tool
        metin = _describe_tool("Write", {"file_path": "A.cs", "content": "   \t\n  "},
                               tam_govde=True)
        self.assertIn("GÖZLE BOŞ", metin)

    def test_bos_HUCRE_uyarisi_defteri_sifirladigini_IDDIA_ETMIYOR(self):
        """`notebook_empty_false_zero_byte_warning`: `Write`'ın "dosya sıfır
        bayta inecek" cümlesi `NotebookEdit`'e de uygulanıyordu, oysa boş bir
        hücre kaynağı defteri sıfırlamıyor. Kartın YANLIŞ bir şey söylemesi, az
        şey söylemesinden kötü."""
        from providers.claude_sdk_session import _describe_tool
        metin = _describe_tool("NotebookEdit", {
            "notebook_path": "analysis.ipynb", "cell_id": "cell-7",
            "new_source": ""}, tam_govde=True)
        self.assertIn("hücre", metin.lower())
        self.assertNotIn("sıfır bayta", metin, "hücre düzenlemesi için yanlış iddia")

    def test_mcp_karti_da_yetkilendirdiginin_tamamini_gosteriyor(self):
        """`mcp_approval_suffix_truncated`: `mcp__`/tanınmayan dal 160 karakterde
        kesiyordu; Onayla sözlüğün tamamını yetkilendirdiği için 160'tan sonraki
        bir `operation=...` alanı görünmüyordu. Yazma dallarındaki kusurun ikizi."""
        from providers.claude_sdk_session import _describe_tool
        yuk = {"dolgu": "A" * 220, "operation": "YIKICI_SON_EK_HERSEYI_SIL"}
        kart = _describe_tool("mcp__unityMCP__manage_scene", yuk, tam_govde=True)
        self.assertIn("YIKICI_SON_EK_HERSEYI_SIL", kart)
        # Çip hâlâ kısa kalmalı — SSE kararı korunuyor.
        cip = _describe_tool("mcp__unityMCP__manage_scene", yuk)
        self.assertNotIn("YIKICI_SON_EK_HERSEYI_SIL", cip)

    def test_gercek_kontrol_ile_DUZ_METIN_kacis_ayirt_edilebiliyor(self):
        """`approval_escape_collision`: gerçek U+202E ile düz metin olarak
        yazılmış `\\u202E` kartta AYNI görünüyordu → iki farklı bayt dizisi
        ayırt edilemiyordu. Ters bölü de kaçırılınca ayrışıyorlar."""
        from providers.claude_sdk_session import _describe_tool
        gercek = _describe_tool("Write", {"file_path": "A.cs", "content": "‮"},
                                tam_govde=True)
        duz = _describe_tool("Write", {"file_path": "A.cs", "content": "\\u202E"},
                             tam_govde=True)
        self.assertNotEqual(gercek, duz, "iki farklı bayt dizisi aynı kartı üretiyor")


class TestDogrulamaTuru2Bulgulari(unittest.TestCase):
    """İkinci doğrulama turunun kartta bulduğu beş kusur (1 Ağu 2026).

    Beşinin de ortak dersi: bir sınıfı kapatmak, o sınıfın KAÇ BİÇİMİ olduğunu
    saymayı gerektiriyor — ilk düzeltme her seferinde bir biçimi kapatıp
    komşusunu açık bırakmıştı.
    """

    def test_tek_ters_bolu_kartta_TEK_gorunuyor(self):
        """`double_escape_write_body`: `_kirp` de kaçırıyordu, çıkış da → tek bir
        ters bölü kartta DÖRT ters bölü oluyordu. Kart, onaylanan içeriği yanlış
        gösteriyordu; "tek çıkış noktası" iddiası da yanlıştı."""
        from providers.claude_sdk_session import _describe_tool
        kart = _describe_tool("Write", {"file_path": "A.cs", "content": "C:\\yol"},
                              tam_govde=True)
        # Tek ters bölü ASLA dörde çıkmamalı — ne başlıkta ne JSON bölümünde.
        # (JSON'da `\\` görünür ve bu JSON dilinde TEK ters bölü demektir;
        # üstüne bir de bizim çiftlememiz binerse gösterim yanlışa döner.)
        self.assertNotIn("\\\\\\\\", kart, "tek ters bölü dört ters bölü olarak gösteriliyor")
        self.assertIn("yol", kart)

    def test_NotebookEdit_HUCRE_TURU_de_kartta(self):
        """`notebook_cell_type_collision`: aynı kaynağı `code` ya da `markdown`
        hücresi olarak eklemek farklı iki işlem, kartları aynıydı."""
        from providers.claude_sdk_session import _describe_tool
        ortak = {"notebook_path": "a.ipynb", "cell_id": "c1",
                 "edit_mode": "insert", "new_source": "print(1)"}
        kod = _describe_tool("NotebookEdit", {**ortak, "cell_type": "code"}, tam_govde=True)
        md = _describe_tool("NotebookEdit", {**ortak, "cell_type": "markdown"}, tam_govde=True)
        self.assertNotEqual(kod, md, "iki ayrı hücre türü aynı kartı üretiyor")

    def test_NotebookEdit_SILME_kipi_etkisini_dogru_soyluyor(self):
        """`notebook_delete_warning_misstates`: `edit_mode="delete"` hücrenin
        KENDİSİNİ siliyor; benim yazdığım "içeriği silinecek" cümlesi etkiyi
        olduğundan küçük gösteriyordu."""
        from providers.claude_sdk_session import _describe_tool
        kart = _describe_tool("NotebookEdit", {
            "notebook_path": "a.ipynb", "cell_id": "c1", "edit_mode": "delete"},
            tam_govde=True)
        self.assertIn("HÜCRE SİLİNİYOR", kart)
        self.assertNotIn("defterin tamamı değil", kart, "silme kipinde yanıltıcı cümle")

    def test_Bash_karti_CALISTIRMA_kipini_de_gosteriyor(self):
        """`bash_fields_omitted`: aynı komutu ön planda 1 sn ya da arka planda
        10 dk çalıştırmak aynı kartı üretiyordu; kullanıcı onayladığı çocuğun
        turdan sonra yaşayıp yaşamayacağını göremiyordu."""
        from providers.claude_sdk_session import _describe_tool
        on = _describe_tool("Bash", {"command": "npm start", "timeout": 1000,
                                     "run_in_background": False}, tam_govde=True)
        arka = _describe_tool("Bash", {"command": "npm start", "timeout": 600000,
                                       "run_in_background": True}, tam_govde=True)
        self.assertNotEqual(on, arka, "iki ayrı çalıştırma kipi aynı kartı üretiyor")
        self.assertIn("run_in_background=True", arka)

    def test_GORUNMEZ_ama_bosluk_olmayan_icerik_hem_uyariyor_hem_gorunuyor(self):
        """`invisible_nonwhitespace_write`: U+3164 HANGUL FILLER boşluk SAYILMIYOR
        (kategori `Lo`) ama mürekkepsiz çiziliyor → `strip()` ölçütünden ve
        `Cf`/`Cc` kaçışından birlikte kaçıyordu."""
        from providers.claude_sdk_session import _describe_tool
        kart = _describe_tool("Write", {"file_path": "A.cs", "content": "ㅤㅤ"},
                              tam_govde=True)
        self.assertTrue("GÖZLE BOŞ" in kart or "\\u3164" in kart,
                        "görünmez içerik ne uyarı üretti ne görünür oldu")


class TestKartYetkilendirilenGirdininTAMAMINI_Gosteriyor(unittest.TestCase):
    """Üçüncü doğrulama turundan sonra ÖLÇÜT DEĞİŞTİ.

    Kart, keyfi bir araç girdisini elle yazılmış düzyazıyla özetliyordu. Özet
    kayıplı olduğu için her tur bir sonraki eksik alanı buldu (`content` →
    `cell_id` → `cell_type` → `run_in_background`). Vaka kapatmak sınıfı
    kapatmıyordu.

    Artık düzyazı yalnızca BAŞLIK; kartın yetkilendirdiğini gösteren bölüm ham
    girdinin kendisi. Bu testler o iki İNŞA GEREĞİ özelliği kolluyor.
    """

    def test_girdideki_HER_alan_kartta_gorunuyor(self):
        from providers.claude_sdk_session import _describe_tool
        yuk = {"file_path": "A.cs", "content": "x", "replace_all": True,
               "beklenmedik_alan": "gizli_deger_42"}
        kart = _describe_tool("Edit", yuk, tam_govde=True)
        for anahtar in yuk:
            self.assertIn(anahtar, kart, f"'{anahtar}' alanı kartta yok")
        self.assertIn("gizli_deger_42", kart)

    def test_iki_FARKLI_girdi_asla_ayni_karti_uretmiyor(self):
        """Çakışma sınıfının kökten kapanışı: JSON farklıysa kart da farklı."""
        from providers.claude_sdk_session import _describe_tool
        a = _describe_tool("Write", {"file_path": "A.cs", "content": ""}, tam_govde=True)
        b = _describe_tool("Write", {"file_path": "B.cs", "content": ""}, tam_govde=True)
        c = _describe_tool("Edit", {"file_path": "A.cs", "old_string": "x",
                                    "new_string": "y", "replace_all": True}, tam_govde=True)
        d = _describe_tool("Edit", {"file_path": "A.cs", "old_string": "x",
                                    "new_string": "y", "replace_all": False}, tam_govde=True)
        self.assertNotEqual(a, b, "iki ayrı boş yazım aynı kartı üretiyor")
        self.assertNotEqual(c, d, "replace_all farkı kartta görünmüyor")

    def test_uyarilar_BILMEDIGIMIZ_bir_etkiyi_iddia_etmiyor(self):
        """Backend dosyanın var olup olmadığını bilmiyor. Eski metin YENİ bir
        dosya yazımında bile "mevcut içerik silinecek" diyordu; boş kaynaklı bir
        `insert` ise "hücrenin içeriği silinecek" diyordu, oysa hücre ekleniyor."""
        from providers.claude_sdk_session import _describe_tool
        yeni = _describe_tool("Write", {"file_path": "YENI.cs", "content": ""}, tam_govde=True)
        self.assertNotIn("mevcut içeriği", yeni)
        ekle = _describe_tool("NotebookEdit", {"notebook_path": "a.ipynb",
                                               "edit_mode": "insert",
                                               "new_source": ""}, tam_govde=True)
        self.assertNotIn("silinecek", ekle.split("── ONAYLANAN")[0],
                         "ekleme işlemi silme gibi anlatılıyor")

    def test_GORUNMEZ_karakter_olcutu_LISTE_degil_KATEGORI(self):
        """Üç turda üç kez aşıldı: `""` → boşluk → U+3164 → varyasyon seçicisi.
        Ölçüt artık 'mürekkep bırakan tek bir karakter var mı'."""
        from providers.claude_sdk_session import _bos_mu
        self.assertTrue(_bos_mu(""))
        self.assertTrue(_bos_mu("   \t\n "))
        self.assertTrue(_bos_mu("ㅤㅤ"))          # U+3164 HANGUL FILLER (Lo)
        self.assertTrue(_bos_mu("︀︁"))  # varyasyon seçicileri (Mn)
        self.assertTrue(_bos_mu("​⁠"))  # sıfır genişlikli (Cf)
        # Gerçek metin etkilenmiyor — aksanın altındaki taban harf görünür:
        self.assertFalse(_bos_mu("é"))
        self.assertFalse(_bos_mu("á"))
        self.assertFalse(_bos_mu("kod"))


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
        # Çip: birebir aynı, kısa.
        self.assertEqual(_describe_tool("Bash", {"command": "git status"}), "git status")
        # Kart: komut BAŞLIKTA duruyor, altında yetkilendirilen girdinin tamamı.
        # (Kartın artık ham girdiyi de taşıması bilinçli — bkz.
        # TestKartYetkilendirilenGirdininTAMAMINI_Gosteriyor.)
        kart = _describe_tool("Bash", {"command": "git status"}, tam_govde=True)
        self.assertTrue(kart.startswith("git status"))
        self.assertIn("ONAYLANAN GİRDİ", kart)


if __name__ == "__main__":
    unittest.main()
