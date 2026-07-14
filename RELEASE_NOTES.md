## Unity Architect AI v2.1.3

Kronik bir MCP WebSocket bağlantı sorunu kökten çözüldü, model kilit sistemi düzeltildi, sohbet ve genel uygulama tasarımı elden geçirildi.

### 🔌 MCP WebSocket "eviction fırtınası" — kökten çözüldü
- **Kök neden bulundu:** Unity'nin arka planda çalışan `AssetImportWorker` süreçleri de MCP köprüsünü başlatıp aynı proje hash'iyle kaydoluyor, ana Editor ile sürekli bağlantı çekişmesine (15-30 saniyede bir "eviction") sebep oluyordu. Artık worker süreçleri köprüyü hiç başlatmıyor.
- **Sonuç:** Önceden dakikada ~16 bağlantı kopması yaşanırken, artık 2 dakikalık canlı testte 0 kopma ölçüldü.
- Ayrıca bağlantı kopuş logları konsoldan temizlendi — sadece kalıcı bağlantı kaybında tek bir kırmızı hata görünüyor, geçici yeniden bağlanmalar artık sessiz.
- Animator child-arama ve `setup_clips` ayar koruması ile ilgili "fake null" kaynaklı düzeltmeler de bu sürümde.

### 🔒 Model kilit sistemi düzeltmesi
- Codex'te "Yenile" sonrası model kilitlerinin (plan limiti nedeniyle) kaybolması giderildi — artık kilit bilgisi korunuyor ve bir model başarıyla yanıt verince otomatik açılıyor.
- Model seçici artık kilit durumunu her açılışta tazeliyor (önceden uygulama yeniden başlatılana kadar bayat kalabiliyordu).

### 🎨 Tasarım yenilemesi
- **Sohbet akışı:** Claude.ai tarzı ferah okuma deneyimi — geniş paragraf boşlukları, başlıklar için ince ayraç çizgiler, tablolar kendi kartında yatay kaydırmalı, "düşünüyor" göstergesi shimmer animasyonlu geçen-süre sayaçlı.
- **Genel arayüz:** Katmanlı yüzey sistemi (daha az düz siyah), aktif modele göre renk değişen marka ışığı (empty state ve Copilot paneli), sidebar ve üst bar rafine edildi.

### 🐛 Diğer
- Unity 6.4'te sürüm-uyum shim'lerinden kaynaklanan CS0618 (obsolete API) sarı derleyici uyarıları susturuldu — davranış değişmedi, sadece gürültü kalktı.

### 🔄 Güncelleme & Güvenlik
Uygulama açılışta yeni sürümü kontrol eder ve **haber verir** — kurulumu sen onaylarsın, sessiz/otomatik kurulum yoktur. Windows'ta kurulum eski sürümü otomatik kaldırır.

> macOS (Apple Silicon) paketi ayrıca eklenecektir.
