## Unity Architect AI v2.1.1

Üç yeni CLI sağlayıcısı, NVIDIA'nın ücretsiz model havuzu, baştan tasarlanan model seçici/ayarlar ve "hiç AI bilmeyenler için" tek-tık CLI kurulumu. Ayrıca kritik bir API-key hatası düzeltildi — güncellemeniz önerilir.

### ✨ Yenilikler
- **🖱️ Cursor, 🐙 GitHub Copilot ve 💻 OpenCode entegrasyonu:** Aboneliğin varsa (Copilot'un ücretsiz tier'ı bile yeter) bu CLI'larla Unity'yi yönetebilirsin — üçü de Unity MCP araçlarına tam erişimli, resmi oturum-devam (resume) destekli. OpenCode'un `opencode/*` modelleri **hesapsız/ücretsiz** çalışır.
- **🟢 NVIDIA NIM (ücretsiz):** [build.nvidia.com](https://build.nvidia.com)'dan alacağın tek ücretsiz API key ile Nemotron 3 Ultra 550B, Qwen 3.5 397B, Mistral Large 3, MiniMax M3, DeepSeek V4 Pro ve Kimi K2.6 — kredi kartsız, ~40 istek/dk.
- **🎛️ Yeni model seçici:** Arama, marka logolu gruplar (7 CLI + 8 API sağlayıcısı), "kurulu değil / ücretsiz / key yok" rozetleri; Cursor ve OpenCode model listeleri hesabına göre canlı gelir.
- **🔐 Plan farkındalığı:** Aboneliğinin desteklemediği modeller (örn. Free planda adlı modeller, ChatGPT hesabında GPT-5.6 Sol) kilitli görünür; yanlışlıkla seçersen otomatik Auto'ya düşer, plan yükseltince ↻ Yenile ile anında açılır.
- **⬇️ Tek-tık CLI kurulumu ve girişi:** CLI kurulu değilse "Kur" butonu resmi kurulumu başlatır, giriş yapılmamışsa "Giriş Yap" tarayıcı akışını açar — terminal bilgisi gerekmez.
- **📁 Git rozetleri:** Dosya ağacında VSCode tarzı değişiklik işaretleri (M/U/A/D + klasör noktası).
- **🖼️ Resim önizleme:** Chat'teki resme tıklayınca artık uygulama içinde tam ekran açılır (beyaz sekme hatası giderildi).
- **⏳ Kota bildirimleri:** CLI kullanım hakkın dolduğunda ham hata yerine anlaşılır mesaj + ücretsiz alternatif önerisi.

### 🐛 Kritik düzeltme
- **API key'in üzerine yazılma hatası:** Abonelik modundan API modeline geçişte kayıtlı gerçek API key'in bozulabiliyordu (401 hatası). Düzeltildi — bu hatayı yaşadıysan key'ini Ayarlar'dan bir kez yeniden girmen yeterli.

### 🔄 Güncelleme & Güvenlik
Uygulama açılışta yeni sürümü kontrol eder ve **haber verir** — kurulumu sen onaylarsın, sessiz/otomatik kurulum yoktur. Windows'ta kurulum eski sürümü otomatik kaldırır.

> macOS (Apple Silicon) paketi ayrıca eklenecektir.
