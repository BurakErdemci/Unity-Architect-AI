## Unity Architect AI v2.2.0

Bu sürümün yıldızı: **VSCode kalitesinde C# kod zekası**. El yapımı linter tarihe karıştı — yerine OmniSharp-Roslyn sidecar geldi. Ayrıca `execute_code` kalıcı olarak düzeldi, effort seçimi artık her modelde gerçek, dosya ağacı tüm Unity dosyalarını gösteriyor ve GLM 5.2 ücretsiz havuza katıldı.

### 🧠 OmniSharp C# Kod Zekası (YENİ)
- **Canlı diagnostics:** Yazarken 1-2 saniyede gerçek derleyici hataları — Unity'nin ürettiği csproj'lardan beslenir, eski linter'ın çapraz-dosya false-positive'leri tamamen bitti.
- **IntelliSense:** `transform.` yazınca gerçek Unity API tamamlama listesi; sembol üstünde hover ile dokümantasyon; Ctrl+tık ile tanıma gitme.
- Workspace açılınca otomatik başlar ("C# analizi hazırlanıyor…" rozeti), Unity kapalıyken de çalışır. Kurulum gerektirmez — pakete gömülü.
- Workspace'te .sln yoksa Unity'den otomatik `sync_csproj` tetiklenir.

### ⚙️ execute_code — "dosya adı çok uzun" kalıcı çözüm
- AI'nın Unity içinde kod çalıştırma aracı artık **Unity'nin kendi derleyicisini** kullanıyor (AssemblyBuilder): dil sürümü her zaman projeninkiyle aynı, oyunun kendi tiplerine (Assembly-CSharp) tam erişim, referans sorunu yapısal olarak imkânsız.
- Derleme hataları temiz formatta doğru satır numarasıyla döner; runtime hataları stack trace ile.

### 🎚️ Effort/Reasoning — artık her modelde GERÇEK
- Seçtiğin düşünme seviyesi artık **tüm** sağlayıcılara gerçekten iletiliyor (önceden çoğunda yok sayılıyordu): Codex `model_reasoning_effort`, Gemini `thinking_level`, Copilot `--effort`, NVIDIA/DeepSeek/Groq/Z.ai reasoning parametreleri…
- **Yeni seçici:** segmented bar yalnız aktif modelin gerçekten desteklediği seviyeleri gösterir; her seviyenin ne yaptığı panelde açıklanır.
- **Auto varsayılanı:** dokunmazsan model kendi akıllı varsayılanıyla çalışır.

### 📁 Dosya ağacı — tüm Unity dosyaları
- Prefab, animasyon, sahne, materyal, FBX, ses… artık hepsi ağaçta (tür bazlı renkli ikonlarla). Unity'nin YAML formatları editörde açılıp düzenlenebilir.
- Guard'lar: binary dosyalar ve 8MB üstü dev dosyalar için bilgilendirici uyarı.

### 🤖 Model havuzu
- **GLM 5.2** (açık ağırlıklı modellerin lideri, 1M bağlam) NVIDIA ücretsiz havuzuna eklendi ve varsayılan yapıldı; **Qwen3 Coder 480B** de katıldı.

### 🛠️ Kararlılık & düzeltmeler
- MCP sunucusunu artık yalnızca uygulamanın toggle'ı başlatır — Unity'nin kendi terminalinde sunucu açıp uygulamanın oturumunu çalması engellendi.
- Editörde imleç/tıklama kayması düzeltildi (font yüklenme yarışı).
- Üst barda uzun dosya yollarının taşması düzeltildi.
- Antigravity (agy): uzun görevlerde ilerleme akışı, kaldığı yerden devam ve yanıt dilinin kullanıcı diline sabitlenmesi.

### 🔄 Güncelleme & Güvenlik
Uygulama açılışta yeni sürümü kontrol eder ve **haber verir** — kurulumu sen onaylarsın, sessiz/otomatik kurulum yoktur. Windows'ta kurulum eski sürümü otomatik kaldırır.

> macOS (Apple Silicon) paketi ayrıca eklenecektir.
