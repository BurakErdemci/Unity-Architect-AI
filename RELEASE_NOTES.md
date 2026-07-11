## Unity Architect AI v2.1.0

2.0.0'dan bu yana büyük bir güncelleme: **videoyu sohbete ekleme**, kalıcı-bağlamlı AI oturumları, güncel modeller, tüm sağlayıcılarda Unity kontrolü ve ciddi token/performans iyileştirmeleri. Bu sürümle **güncelleme bildirimi** de geliyor — yeni sürüm çıktığında uygulama sana haber verir (kurulumu sen onaylarsın; sessiz/otomatik kurulum yapılmaz).

### ✨ Yenilikler
- **🎬 Video → sohbet:** Videoyu doğrudan chat'e ekle — yerel dosya seç veya URL'yi mesaja yapıştır. Tüm AI'lar videoyu kare + altyazı olarak "görür", sağlayıcıdan bağımsız. ffmpeg + yt-dlp gömülü, ekstra kurulum yok.
- **🔁 Kalıcı-bağlamlı oturumlar:** Claude Code (native onay + SDK), Codex (app-server, native onay) ve agy artık kalıcı oturumda çalışıyor. CLI'lar arası bağlam sürekliliği — Claude ↔ Codex ↔ agy geçişinde geçmiş korunur.
- **🧠 Güncel modeller:** Claude Sonnet 5 / Opus 4.8 / Fable 5, DeepSeek V4, GLM 5.2, Kimi K2.7, GPT-5.6 (Sol/Terra/Luna), Gemini 3.5 Flash — tek effort seçici.
- **🛠️ Tüm sağlayıcılarda Unity MCP:** Artık Gemini ve Anthropic (API) da 45+ Unity aracını kullanabiliyor (önceden yalnız OpenAI). Direkt GLM/Kimi de tam agentic yola alındı.
- **⏱️ Token footer** her sağlayıcıda (süre + input/output token) + `/usage` ve `/context` slash-komut kartları + Skills galerisi.

### ⚡ Performans
- **Input-token tüketimi ciddi düşürüldü:** koşullu MCP keşfi (basit soru artık 7 tur yerine 1 tur), transcript kırpma ve prompt caching (Anthropic native + OpenRouter). Basit sorular çok daha az token yiyor.

### 🐛 Düzeltmeler
- Paketlenmiş build'de Unity MCP tam çalışır; güvenlik sıkılaştırmaları (fail-closed onay, path traversal koruması, token zorunluluğu); silinen/taşınan workspace'in zarif ele alınması; model kimliği düzeltmesi (model artık "ben Claude'um" demez); Gemini MCP 400 fix; agy konsol-penceresi parlaması fix.

### 🔄 Güncelleme & Güvenlik
Uygulama açılışta yeni sürümü kontrol eder ve varsa sana **haber verir** — "İndirme sayfasını aç" ile resmi release sayfasına gidersin, kurulumu sen yaparsın. **Sessiz/otomatik kurulum yoktur** (güvenlik: imzasız otomatik güncelleme riski taşımaz).

---

### 📥 Kurulum

- **Windows:** `Unity-Architect-AI-Setup-2.1.0.exe` — indir ve çalıştır. SmartScreen çıkarsa → **More info → Run anyway** (imzasız test build).
- **macOS:** `.dmg` dosyasını indir, uygulamayı Applications'a sürükle. İlk açılışta Gatekeeper uyarısı çıkarsa: **Sağ tık → Aç** (imzasız build). Anahtarlık erişimi istenirse şifreni gir ve **Her zaman izin ver** seç (API anahtarların güvenli saklansın diye).

> ffmpeg / yt-dlp / uv araç zinciri ve Unity MCP sunucusu **gömülü** — kullanıcı hiçbir şey ayrıca kurmaz.
