# Değişiklik günlüğü

Bu dosya kullanıcıya görünen değişiklikleri taşır. Tam geçmiş için `git log`.

## v2.3.0 — 2 Ağustos 2026

**Bu sürüm bir güvenlik sürümüdür.** v2.2.0'dan bu yana 125 commit geldi ve
100'ü düzeltme; ağırlığı, ürünün sırlarını, onay kapısını ve dosya erişimini
sertleştiren çalışma oluşturuyor. v2.2.0 kullanan herkesin güncellemesi
öneriliyor.

### 🔐 Güvenlik

**Yerel sır (backend ↔ Unity MCP paylaşımlı anahtarı)**
- Sır artık URL'de değil `X-API-Key` başlığında taşınıyor. Eskiden adres
  çubuğuna, log satırlarına ve süreç listelerine düşebiliyordu.
- Sır hiçbir CLI yapılandırma dosyasına yazılmıyor.
- Token dosyası Windows'ta ACL ile kilitli, yazımlar atomik; kimlik doğrulaması
  yola değil **açılmış dosya tanıtıcısına** bakıyor (sembolik bağ/junction ile
  yönlendirme kapandı).
- Sırrın hem yeni hem eski biçimi loglarda maskeleniyor.

**Prompt ve komut satırı**
- Kullanıcı prompt'u artık süreç argümanlarında taşınmıyor. Eskiden makinedeki
  herhangi bir süreç süreç listesinden prompt'un tamamını okuyabiliyordu.
- `[CMD]` kaydı prompt'un tamamını kalıcı bir dosyaya yazmıyor.

**Onay kapısı**
- Kapı Unity MCP boğazına kondu: **dokuz sağlayıcının dokuzu da** artık aynı
  kapıdan geçiyor. Öncesinde araç çağrıları kapıyı hiç görmüyordu.
- Kapı REST rotası üzerinden de atlatılamıyor.
- `delete_file` kapıya alındı.
- **Yazma onay kartı artık ne yazılacağını gösteriyor** — kart, yetkilendirilen
  girdinin tamamını taşıyor; öncesinde göremediğin bir şeyi onaylıyordun.
- Kart hangi projenin değişeceğini söylüyor; eşzamanlı adım turlarında
  otomatik onay "en az biri" değil "hepsi" kuralına bağlandı.
- Kullanıcının açtığı bir proje kapıyı devre dışı bırakamıyor.
- Codex onay hakemi `user` olarak sabitlendi ve yanıttan doğrulanıyor: onay
  isteği artık bir dil modeline devredilemiyor.

**Masaüstü uygulaması**
- **İçerik Güvenliği Politikası (CSP)** eklendi; Monaco editörü CDN yerine
  yerelden servis ediliyor — uygulama artık çalışmak için dış bir sunucuya
  bağlanmıyor.
- IPC çağrıları için kaynak kapısı: yalnız uygulamanın kendi sayfası çağırabilir.
- Workspace kökü yalnızca kullanıcının native diyalogla seçtiği bir yol olabilir.
- Uygulama uzak bir sayfaya gidemiyor, yeni pencere açamıyor, `<webview>`
  ekleyemiyor; dış linkler işletim sisteminin tarayıcısına gidiyor.

**Dosya erişimi**
- Sembolik bağ, junction, **sabit bağ** ve NTFS alternatif veri akışı yoluyla
  workspace dışına çıkma yolları kapatıldı.
- Okuma kapısında kontrol/kullanım yarışı kapatıldı: kapının onayladığı dosya
  ile okunan dosya artık aynı olmak zorunda, ve bu açılmış tanıtıcının
  kimliğiyle doğrulanıyor.
- Yapılandırma yazımları workspace dışındaki bir dosyanın üstüne yazamıyor.

**Diğer**
- Komut onay kapısındaki ön ek eşleşme atlatması kapatıldı.
- Ortam değişkeni sızıntısı sınıfı kapatıldı (ad eşleşmesi değil **değer**
  eşleşmesi).
- İndirilen tüm ikililer (OmniSharp, .NET SDK, uv, ffmpeg, yt-dlp) sabitlenmiş
  bir kütüğe ve özet doğrulamasına bağlandı.
- Kullanıcı projesine yazılan yapılandırma dosyaları `.gitignore`'a alındı.

### ✨ Yenilikler

- **Claude Opus 5** desteği.
- **Kimi K3 / Kimi CLI** sağlayıcısı.
- **Gemini 3.6** ve **Gemini 3.5 Lite**.
- OmniSharp için **.NET SDK pakete gömüldü** (macOS/Linux) — sıfır kurulum.
- Unity MCP: N+1 sorgu iyileştirmesi, kısmi eşleşme, toplu işlem zincirleme,
  kota/round-trip/no-op davranışları.

### 🐛 Düzeltmeler

- **Sohbetteki dosya linki artık dosyayı açıyor.** Yeşil dosya adına
  tıklayınca uygulama "resetleniyor" gibi görünüyordu — aslında pencere o
  adrese gidip arayüzü boşaltıyordu.
- **Beklenmedik veri artık tüm pencereyi boşaltmıyor:** uygulamaya bir hata
  sınırı eklendi, hata beyaz ekran yerine okunabilir bir panel gösteriyor.
- Model listesi bayat bir kapanış değeri yüzünden tüm API modellerini
  gizleyebiliyordu.
- Unity MCP, Editor'da domain reload sonrası yeniden bağlanmayı sürdürüyor.
- C# projesi (`csproj`) üretimi artık harici bir IDE kurulu olmasına bağlı değil.
- C# hover'ının asılması giderildi.
- `execute_code`'un atlatılabildiği yer düzeltildi.
- Windows'ta ürünün tamamını çalışmaz hale getirebilen üç hata giderildi.
- Uygulamanın kendi bağlantı afişi kendi onay kapısına takılıyordu.

### 📄 Lisans

- Proje **MIT + Commons Clause** ile lisanslandı; üçüncü parti bildirimleri eklendi.

### 🧪 Kalite

- Unity MCP sunucu test suite'i (1522 test) kalite kapısına bağlandı.
- Testler Windows'ta koşabilir hale getirildi; bu çalışma üç ürün hatası ortaya
  çıkardı.
- Dört bağımsız denetim turu koşuldu (biri tamamen dış gözle); üretilen
  bulguların tamamı kanıtlanabilir probe'larla üretildi ve kapatıldı.

### ⚠️ Bilinenler

- macOS derlemesi yalnız **Apple Silicon (arm64)**.
- Otomatik güncelleme **yalnız bildirim** yapar; indirme ve kurulum kullanıcıya
  bırakılır (uygulama imzasız olduğu için sessiz kurulum bilerek kapalı).
