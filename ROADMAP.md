# Unity Architect AI — 1.5 Aylık Geliştirme Planı

## Öncelik Sırası
- 🔴 Kritik (Projenin en büyük değeri)
- 🟠 Yüksek (Kullanıcı deneyimini ciddi artırır)
- 🟡 Orta (Cilalama & profesyonellik)

---

## FAZA 1: KB Sistemini Güçlendir (Hafta 1-2)
> Hedef: Local sistem API key olmadan başlangıç seviyesi Unity projelerini karşılasın

### 🔴 1.1 — KB Şablon Sayısını 20-25'e Çıkar
Mevcut: 5 şablon (movement, pooling, singleton, state_machine, events)

Eklenecek şablonlar:
- [x] **Karakter Kontrolcüsü 2D** (Platformer — hareket + zıplama + duvar kayma)
- [x] **Karakter Kontrolcüsü 3D** (FPS/TPS — mouselook + WASD)
- [x] **Jump Sistemi** (Coyote time, jump buffer, variable height)
- [x] **Health/Damage Sistemi** (IDamageable interface, HP bar)
- [x] **Inventory Sistemi** (ScriptableObject tabanlı, slot UI)
- [x] **Save/Load Sistemi** (JSON serialization, PlayerPrefs alternatifi)
- [x] **UI Manager** (Panel açma/kapama, animasyonlu geçişler)
- [x] **Audio Manager** (SFX + müzik, pooling ile ses yönetimi)
- [x] **Camera Follow** (Smooth follow, cinemachine alternatifi, screen shake)
- [x] **Spawn/Wave Sistemi** (Enemy spawner, wave manager, difficulty scaling)
- [x] **Dialogue Sistemi** (Basit NPC diyalog, ScriptableObject ile veri)
- [x] **Scene Manager** (Sahne geçişi, loading screen, async load)
- [x] **Input Sistemi** (New Input System wrapper, rebind desteği)
- [x] **Projectile/Shooting** (Mermi sistemi, raycast vs fizik, pooling ile)
- [x] **Collectible/Pickup** (Toplanabilir obje, mıknatıs efekti, skor)
- [x] **Animation Controller** (Animator parametreleri, state geçişleri, blend tree)
- [x] **Parallax Background** (2D arka plan katmanları, sonsuz kaydırma)
- [x] **Pathfinding** (A* basit grid, NavMesh kullanımı)
- [x] **Timer/Countdown** (Zamanlayıcı, cooldown sistemi)
- [x] **Minimap** (Render texture tabanlı minimap)

### ✅ 1.2 — Parametrik Şablon Sistemi
KB JSON'da `group` + `variant_tags` alanları. `kb_engine.py`'de `_detect_variant()` ile query'den 2D/3D/FPS/Platformer sinyali algılama.

### ✅ 1.3 — Wizard Soru-Cevap Akışı
`clarification_needed=True` + `format_clarification()`: Varyant belirtilmeden sorulunca sistem seçenek sorar.
Kullanıcı "karakter kontrolcüsü yaz" → "2D Platformer mı, 3D FPS mi?" → cevaba göre doğru şablon.

### ✅ 1.4 — Unity Kurulum Rehberi
Tüm 28 entry'ye `setup_steps` alanı eklendi. `format_response()` çıktısında "📋 Unity Kurulum Adımları" bölümü otomatik gösterilir.

---

## FAZA 2: Dosya Sistemi Entegrasyonu (Hafta 2-3)
> Hedef: Üretilen kodu doğrudan Unity projesine yazma

### ✅ 2.1 — "Unity'ye Aktar" Butonu
- [x] Chat'te üretilen kodun altına "📁 Unity Projesine Aktar" butonu
- [x] Tıklandığında seçili workspace'in `Assets/Scripts/` altına `.cs` dosyası yazar
- [x] Dosya adını otomatik belirle (class name'den)
- [x] Zaten varsa "Üzerine yaz / Yeni isimle kaydet" sor
- [x] Kullanıcı hedef dizini değiştirebilir (klasör seçim diyalogu)

### ✅ 2.2 — Çoklu Dosya Export
Bir sistem birden fazla script gerektiriyorsa (ör: Inventory = 3 dosya):
- [x] Tüm dosyaları tek seferde yaz
- [x] Klasör yapısını oluştur
- [x] Sonuç raporu göster: "3 dosya oluşturuldu ✓"

### 🟡 2.3 — Mevcut Kodu Düzenleme *(Ertelendi → Faz 5+)*
- [ ] Kullanıcı workspace'ten bir dosya açtığında, AI/KB önerisini mevcut koda uygulasın
- [ ] Diff görünümü: "Bu satırlar değişecek" önizlemesi (Monaco DiffEditor ile)
- [ ] Onay sonrası dosyayı güncelle

---

## FAZA 3: Güvenlik ve Veri Bütünlüğü (Hafta 3-4)
> Hedef: Mevcut kritik açıkları kapatıp dosya sistemi ve kullanıcı verisini güvenli hale getirme

### 🔴 3.1 — Session Tabanlı Auth + Endpoint Authorization
- `user_id`'ye güvenen tüm endpoint'leri session/token tabanlı hale getir
- Her istekte sunucu tarafında "isteği yapan kullanıcı kim?" bilgisi doğrulansın
- `history`, `conversations`, `messages`, `api_keys`, `workspace` endpoint'lerinde kaynak sahipliği kontrolü ekle
- `conv_id`, `item_id`, `user_id` tahmin edilse bile başka kullanıcının verisi okunamasın/değiştirilemesin

### 🔴 3.2 — API Key Güvenliği
- `/get-ai-config` gerçek `api_key` döndürmesin; sadece `provider_type`, `model_name`, `use_multi_agent`, `has_key` bilgisi dönsün
- API key yalnızca backend'de kullanılsın, frontend'e asla plaintext taşınmasın
- İleride mümkünse key'leri OS keychain veya şifreli local storage ile sakla
- "Vault" mantığını gerçek hale getir: maskeleme sadece UI değil, veri akışında da uygulansın

### 🔴 3.3 — Güvenli Dosya Yazma Katmanı
- `/update-file` endpoint'ini kaldır veya workspace sandbox içine al
- `startswith` yerine `Path.resolve()` + ebeveyn dizin doğrulaması kullan
- Yazma iznini sadece seçili workspace altındaki güvenli klasörlerle sınırla
- Varsayılan export hedefini `Assets/Scripts/` ile kısıtla; workspace dışı path reddedilsin
- Dosya overwrite işlemleri için onay + diff zorunlu olsun

### 🟠 3.4 — Sohbet ve Geçmişte Veri Sahipliği Kuralları
- `conversation_id -> user_id` eşlemesini zorunlu doğrula
- Mesaj ekleme, silme, yeniden adlandırma işlemlerinde ownership check ekle
- Geçmiş detayları (`analysis-detail`, `history`) sadece ilgili kullanıcı tarafından erişilebilir olsun
- DB katmanında bu kontroller için ayrı yardımcı metodlar oluştur; endpoint içinde ham query mantığı kalmasın

### 🟠 3.5 — Güvenlik Testleri ve Regression Koruması
- Endpoint authorization testleri ekle
- Workspace path traversal testleri ekle
- API key'in response body'de plaintext dönmediğini test et
- Çok kullanıcılı senaryolar için integration test yaz: User A, User B'nin sohbetine erişememeli
- Release öncesi güvenlik checklist'i oluştur

### 🟡 3.6 — Repo Hijyeni ve Secret Temizliği
- `__pycache__`, build artifaktları ve `tsconfig.tsbuildinfo` gibi dosyaları `.gitignore` altına al
- Repo içinde gerçek DB veya secret kalıntısı var mı tarayan basit bir pre-release kontrol ekle
- Loglarda API key, access token, OAuth response gibi hassas veriler maskelensin

---

## FAZA 4: Teknik Sağlamlaştırma ve Mimari Temizlik (Hafta 4-5)
> Hedef: Güvenlik sonrası sistemi kırılmadan büyütebilmek için backend, pipeline ve test yapısını sertleştirme

### 🔴 4.1 — `main.py` Parçalama ve Modüler Backend Yapısı
- `main.py` içindeki auth, OAuth, chat, file I/O, config, conversation endpoint'lerini router/modül bazlı ayır
- İş kurallarını service katmanına taşı; endpoint'ler sadece request/response yönetsin
- DB erişimini route içinden değil, servis/helper katmanından geçir
- Amaç: tek dosyada yığılmış business logic'i azaltmak ve refactor riskini düşürmek

### 🔴 4.2 — Test Kapsamını Gerçek Kritik Akışlara Taşı
- Sadece validator/intent değil, endpoint + integration + DB testleri ekle
- Pipeline seçim mantığını test et: KB / SingleAgent / MultiAgent doğru dallanıyor mu
- DB migration ve conversation lifecycle testleri yaz
- Workspace export, overwrite, diff-confirmation akışları test edilsin
- "pytest yok" gibi environment bağımlılıklarını çözmek için test komutunu standartlaştır

### 🔴 4.3 — Pipeline Progress ve Durum Modelini Düzelt
- SingleAgent ve MultiAgent için ortak step sözleşmesi oluştur
- UI'ın beklediği adımlarla backend'in ürettiği progress event'leri birebir eşleşsin
- `step3`, `step4`, retry ve failure durumları açık ve tutarlı modellensin
- Timeout, partial success ve retry senaryoları kullanıcıya doğru yansıtılsın

### 🟠 4.4 — Import / Packaging Dayanıklılığı
- Doğrudan modül importlarını package-relative yapıya çek
- Backend farklı çalışma dizinlerinden ayağa kalkabiliyor mu doğrula
- Electron build ile development ortamı arasında import/path farklarını minimize et
- Packaging sonrası "lokalde çalışıyor ama build'de kırılıyor" sınıfı hataları azalt

### 🟠 4.5 — Dokümantasyon ve Gerçek Sistem Eşleştirmesi
- README'deki claim'leri kodla tek tek karşılaştır
- Çalışmayan/yarım özellikleri ya tamamla ya da dokümantasyondan düşür
- "Vault", "Multi-Agent", "Workspace güvenliği", "skorlama" gibi iddialı başlıklar implementasyonla tutarlı olsun
- Demo metni ile gerçek ürün arasında beklenti farkı kalmasın

### 🟡 4.6 — Operasyonel Gözlemlenebilirlik
- Pipeline adımlarına structured logging ekle
- Hangi provider neden hata verdi, hangi step ne kadar sürdü görülebilsin
- Debug log ile production log seviyeleri ayrıştırılsın
- Hata ayıklama için minimum faydalı telemetry çıkarılsın

---

## FAZA 5: UX İyileştirmeleri (Hafta 5-6)
> Hedef: Profesyonel, hatasız kullanıcı deneyimi

### 🟠 5.1 — Backend Health Check & Splash Screen
- Uygulama açılışında splash screen göster
- `/health` endpoint'ine ping at
- Backend hazır olana kadar "Sistem başlatılıyor..." göster
- Hazır olunca ana ekrana geç
- Windows'taki "backend hazır değil" sorunu çözülür

### 🟠 5.2 — Toast Notification Sistemi
- `react-hot-toast` veya benzeri kütüphane
- Hata: kırmızı toast (API hatası, bağlantı sorunu)
- Başarı: yeşil toast (dosya kaydedildi, kod kopyalandı)
- Bilgi: mavi toast (backend başlatılıyor)
- Beyaz çerçeve hata mesajları tarih olsun

### 🟠 5.3 — Kod Önizleme İyileştirmesi
- Monaco Editor ile üretilen kodu göster (şu an markdown code block)
- Satır numaraları, syntax highlighting, minimap
- Inline edit yapabilme (küçük düzeltmeler)
- "Kopyala" + "Unity'ye Aktar" butonları yan yana

### 🟡 5.4 — Loading & Progress UX
- AI yanıt beklerken skeleton loading
- Pipeline adımları için animasyonlu progress bar
- KB yanıtlarında "⚡ Anında Yanıt" badge'i (AI kullanılmadığını gösterir)

---

## FAZA 6: AI İllüzyonu — Akıllı KB (Hafta 6-7)
> Hedef: KB yanıtları AI gibi doğal ve kişiselleştirilmiş hissettirsin

### 🔴 6.1 — Doğal Dil Cevap Şablonları
KB yanıtları şu an mekanik. Doğal konuşma tonu ekle:

```
Eski: "## Movement Basic\n```csharp\n..."
Yeni: "Karakter hareketi için Rigidbody tabanlı bir sistem hazırladım.
FixedUpdate kullanıyorum çünkü fizik işlemleri sabit zamanlama gerektirir.
İşte kodun: ..."
```

- Her şablon için 3-4 farklı giriş cümlesi (rastgele seçilir)
- Kullanıcının sorusundaki kelimeleri cevaba yansıt

### 🟠 6.2 — Bağlam Takibi (Session Context)
- Kullanıcı daha önce ne sordu hatırla
- "Buna zıplama da ekle" → önceki karakter kontrolcüsüne jump ekle
- "Bunu 3D yap" → önceki 2D şablonun 3D versiyonunu ver
- Basit state machine ile conversation context tut

### 🟠 6.3 — Hata Tanıma & Çözüm Önerisi
Kullanıcı hata yapıştırdığında:
- Bilinen Unity hatalarını regex ile tanı (NullReferenceException, MissingComponentException vb.)
- Hazır çözüm öner: "GetComponent<Rigidbody2D>() null dönüyor → Awake'te cache'le, objeye component eklenmiş mi kontrol et"
- Sık yapılan hataların veritabanı

### 🟡 6.4 — Kombine Sistem Önerileri
Kullanıcı "Platformer oyun yapıyorum" derse:
- Tek şablon değil, bir **sistem paketi** öner:
  - ✅ 2D Karakter Kontrolcüsü
  - ✅ Jump Sistemi
  - ✅ Camera Follow
  - ✅ Collectible/Pickup
  - ✅ Health Sistemi
- "Hepsini kur" butonu → tüm scriptleri Unity projesine yaz

---

## FAZA 7: Dashboard & Analytics (Hafta 7-8)
> Hedef: Profesyonel görünüm, sunum/demo için etkileyici

### 🟡 7.1 — Kullanıcı Dashboard'u
- Toplam üretilen kod sayısı
- En çok kullanılan şablonlar (pie chart)
- AI vs KB kullanım oranı
- Son aktivite timeline'ı

### 🟡 7.2 — Kod Kalite Trendi
- Her analiz/üretimde Game Feel skoru kaydedilsin
- Zaman içindeki skor değişimini grafik olarak göster
- "Kodunuz son 1 haftada %15 iyileşti" gibi motivasyon mesajları

### 🟡 7.3 — Provider Performans Karşılaştırma
- Hangi AI provider ne kadar hızlı yanıt veriyor
- Ortalama token kullanımı
- Başarı/hata oranları

---

## FAZA 8: Son Cilalama & Build (Hafta 8)
> Hedef: Dağıtıma hazır, kararlı build

### 🟡 8.1 — Prompt Şablonları (Quick Actions)
- Chat input altında hazır butonlar:
  - "🎮 Karakter Kontrolcüsü"
  - "📦 Inventory Sistemi"
  - "💾 Save/Load"
  - "🔊 Audio Manager"
- Tek tıkla wizard başlasın

### 🟡 8.2 — Onboarding / İlk Kullanım Deneyimi
- Yeni kullanıcı için adım adım tanıtım turu
- "Workspace seç → İlk kodunu üret → Unity'ye aktar" akışı
- KB modunu tanıt: "API key gerekmez, hemen başla!"

### 🟡 8.3 — Final Build
- macOS + Windows build
- Test: tüm KB şablonları çalışıyor mu
- Test: dosya export çalışıyor mu
- Test: kullanıcı A, kullanıcı B'nin verilerine erişemiyor mu
- Test: API key frontend'e plaintext dönmüyor mu
- Test: packaged build'de import/path sorunları çıkmıyor mu
- Test: progress UI gerçek pipeline adımlarıyla tutarlı mı
- Test: offline (internetsiz) KB modu çalışıyor mu
- README güncelle
- GitHub release oluştur

---

## FAZA 9: Adaptive Intelligence — Akıllı Soru-Cevap & Modüler Üretim (Hafta 9-10)
> Hedef: Sistem basit işleri tek atışta, karmaşık işleri soru sorarak ve parça parça çözsün

### 🔴 9.1 — Complexity Gate (Karmaşıklık Kapısı)
Her iki pipeline'da (SingleAgent + MultiAgent) kullanıcı isteğinin karmaşıklığını değerlendir:

```
Kullanıcı Promptu → Intent Classifier → Complexity Gate
                                            │
                                       ┌────┴────┐
                                      LOW       HIGH
                                       │         │
                                       ▼         ▼
                                    Mevcut    Clarification
                                    Pipeline    Loop
                                    (tek atış)  (soru-cevap)
```

- **SingleAgent:** Prompt seviyesinde çözüm — mevcut system prompt'a "karmaşık isteklerde kod yazma, önce soru sor" talimatı
- **MultiAgent:** Ayrı `ComplexityAssessorAgent` ajanı — LLM tabanlı analiz

### 🔴 9.2 — Clarification Loop (Netleştirme Döngüsü)
Karmaşık istek tespit edildiğinde AI, kod yazmadan önce kullanıcıdan detay toplar:

```
Kullanıcı: "Ansiklopedi sistemi yap"

AI: "📚 Sistemi en iyi şekilde tasarlamam için birkaç soru:
     1. Ne tür veriler içerecek? (Lore / Karakter bilgisi / Item DB)
     2. Verileri nasıl saklamak istersin? (ScriptableObject / JSON / SQLite)
     3. UI gerekiyor mu? Arama/filtreleme olsun mu?"

Kullanıcı: "Oyun içi lore, ScriptableObject ile, basit UI + arama"

AI: → Yeterli bilgi toplandı → Zenginleştirilmiş prompt → Pipeline tetiklenir
```

Kurallar:
- **Soru limiti yok** — AI tatmin olana kadar sorar
- Sorular **toplu** sorulur (tek mesajda 3-4 soru), tek tek sorulmaz
- Basit isteklerde soru sorulmaz, direkt üretilir (mevcut davranış korunur)
- Arka planda **requirements.json** biriktirilir (kullanıcıya görünmez)

### 🔴 9.3 — Code Accumulator (Modüler Kod Biriktirici)
Karmaşık sistemlerde tek seferde dev bir kod bloğu yerine **parça parça** üretim:

```
┌─────────────────────────────────────────┐
│        Code Accumulator (Gizli)         │
│                                         │
│  // === LoreEntry.cs ===                │
│  (✅ Tamamlandı - 45 satır)             │
│                                         │
│  // === LoreDatabase.cs ===             │
│  (✅ Tamamlandı - 60 satır)             │
│                                         │
│  // === LoreManager.cs ===              │
│  (⏳ Yazılıyor...)                      │
│                                         │
│  // === LoreUI.cs ===                   │
│  (📋 Sırada)                            │
└─────────────────────────────────────────┘
```

- AI planı çıkarır → Her dosyayı ayrı ayrı üretir → Accumulator'a kaydeder
- Token limitine yaklaşırsa kullanıcıya sorar: _"3 dosyayı tamamladım, devam edeyim mi?"_
- Tümü bitince birleşik sonucu sunar
- **Timeout riski sıfırlanır** — her parça küçük ve hızlı
- **Yarım kalan kod sorunu çözülür** — birikim sistemi parçaları tutar

### 🟠 9.4 — Gizli Context Yönetimi
AI'ın arka planda tuttuğu, kullanıcıya gösterilmeyen bilgi katmanı:

- `requirements.json` — Toplanan gereksinimler (soru-cevap turlarından)
- `accumulated_code` — Şu ana kadar üretilen tüm kod parçaları
- Conversation DB'sine `metadata` olarak saklanır
- Yeni mesajlarda context olarak AI'a gönderilir, kullanıcıya gösterilmez

---

## Özet Timeline

| Hafta | Faz | Ana Odak |
|-------|-----|----------|
| 1-2 | Faz 1 | KB şablonları + parametrik sistem + wizard |
| 2-3 | Faz 2 | Dosya sistemi entegrasyonu (Unity'ye aktar) |
| 3-4 | Faz 3 | Güvenlik, authorization, secret yönetimi, dosya sandbox |
| 4-5 | Faz 4 | Mimari temizlik, test kapsamı, pipeline doğruluğu |
| 5-6 | Faz 5 | UX iyileştirmeleri (toast, health check, loading) |
| 6-7 | Faz 6 | AI illüzyonu (doğal dil, bağlam, hata tanıma) |
| 7-8 | Faz 7 | Dashboard & analytics |
| 8 | Faz 8 | Cilalama, build, test, dağıtım |
| 9-10 | Faz 9 | Adaptive Intelligence (soru-cevap + modüler üretim) |

---

## Başarı Kriterleri
- ✅ Yeni başlayan biri API key olmadan temel Unity projesi oluşturabilir
- ✅ KB 20+ şablonla yanıt verir, kullanıcı AI sandığı doğal cevaplar alır
- ✅ Üretilen kod tek tıkla Unity projesine aktarılır
- ✅ Hata mesajları profesyonel, uygulama kararlı
- ✅ Offline çalışır (KB modu)
- ✅ Kullanıcı verileri ve API key'ler başka oturumlar tarafından okunamaz
- ✅ Dosya yazma işlemleri sadece izinli workspace altında gerçekleşir
- ✅ Backend modülerdir; tek dosyalık kırılgan yapı azalır
- ✅ Kritik akışlar otomatik testlerle korunur
- ✅ Progress/pipeline davranışı UI ile tutarlı çalışır
- ✅ Karmaşık isteklerde AI soru sorarak detay toplar, sonra üretir
- ✅ Büyük sistemler parça parça üretilir, timeout/yarım kod sorunu olmaz
