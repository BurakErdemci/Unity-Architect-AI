<div align="center">

# 🏗️ Unity Architect AI

**Yapay Zeka Destekli Unity C# Kod Analiz, Denetim ve Sıfırdan Kod Üretim Platformu**

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Electron](https://img.shields.io/badge/Electron-34-47848F?style=for-the-badge&logo=electron&logoColor=white)](https://electronjs.org)
[![Next.js](https://img.shields.io/badge/Next.js-14-000000?style=for-the-badge&logo=next.js&logoColor=white)](https://nextjs.org)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://reactjs.org)
[![Anthropic](https://img.shields.io/badge/Claude-API-191919?style=for-the-badge&logo=anthropic&logoColor=white)](https://anthropic.com)

*Unity geliştiricileri için Multi-Agent AI ile profesyonel seviyede kod denetimi, oyun hissiyatı (Game Feel) analizi ve sıfırdan Enterprise-level kod üretimi.*

---

[![AI Karşılaştırması](https://img.shields.io/badge/🤖_AI_Karşılaştırması-Modelleri_Gör-6366f1?style=for-the-badge)](./AI_COMPARISON.md)

---

## ⬇️ İndir

| Platform | İndirme Linki |
|----------|---------------|
| 🍎 macOS (Apple Silicon — arm64) | [Unity.Architect.AI-1.0.0-arm64.dmg](https://github.com/BurakErdemci/Unity-Architect-AI/releases/download/v1.0.0/Unity.Architect.AI-1.0.0-arm64.dmg) |
| 🍎 macOS (Universal — Intel + Apple Silicon) | [Unity.Architect.AI-1.0.0.dmg](https://github.com/BurakErdemci/Unity-Architect-AI/releases/download/v1.0.0/Unity.Architect.AI-1.0.0.dmg) |
| 🪟 Windows | [Unity Architect AI Setup 1.0.0.exe](https://github.com/BurakErdemci/Unity-Architect-AI/releases/download/v1.0.0/Unity%20Architect%20AI%20Setup%201.0.0.exe) |

> Tüm sürümler için: [GitHub Releases →](https://github.com/BurakErdemci/Unity-Architect-AI/releases)

> **macOS uyarısı:** "Hasar görmüş" hatası alırsanız Terminal'de şu komutu çalıştırın:
> ```bash
> xattr -cr /Applications/Unity\ Architect\ AI.app
> ```

</div>

## 📋 İçindekiler

- [Özellikler](#-özellikler)
- [Multi-Agent Mimarisi](#-multi-agent-mimarisi)
- [Pipeline Sistemi](#-pipeline-sistemi)
- [Mimari](#-mimari-genel-bakış)
- [Güvenlik Mimarisi](#-güvenlik-mimarisi)
- [Geliştirme Hikayeleri](#-geliştirme-hikayeleri--alınan-dersler)
- [Kurulum](#-kurulum)
- [Kullanım](#-kullanım)
- [Teknoloji Yığını](#-teknoloji-yığını)
- [Proje Yapısı](#-proje-yapısı)
- [API Dokümantasyonu](#-api-dokümantasyonu)
- [Yol Haritası](#-yol-haritası)
- [Lisans](#-lisans)

---

## ✨ Özellikler

### 🧠 LLM Tabanlı Akıllı Niyet Algılama (Intent Classification)

Kullanıcı mesajlarını analiz edip **doğru pipeline'a** yönlendiren hibrit bir sınıflandırıcı:

| Niyet | Tetiklenme | Pipeline |
|-------|------------|----------|
| `GREETING` | "Merhaba", "Nasılsın" | Direkt selamlama yanıtı |
| `GENERATION` | "FPS hareket sistemi yaz", "Envanter sistemi oluştur" | Sıfırdan Kod Üretim Pipeline'ı |
| `ANALYSIS` | "Bu kodu analiz et", C# kodu algılandığında | Multi-Agent Analiz Pipeline'ı |
| `CHAT` | "Unity'de NavMesh nedir?" | Genel sohbet |
| `OUT_OF_SCOPE` | "Yemek tarifi ver" | Kibar reddetme |

> İki katmanlı yaklaşım: **Hızlı statik filtre** (regex) + **LLM fallback** (belirsiz durumlarda Claude/Groq ile sınıflandırma).

### 🎮 Oyun Hissiyatı (Game Feel) Analizi

Kod kalitesinin ötesinde, **oyuncunun kodu çalıştırdığında ne hissedeceğini** puanlayan benzersiz bir ajan:

| Kategori | Ağırlık | Örnek Kontrol |
|----------|---------|---------------|
| 🕹️ Hareket | %30 | Snappy vs Floaty? rb.velocity vs AddForce? |
| ⚔️ Combat | %25 | Input → Aksiyon gecikmesi? Feedback var mı? |
| 🎯 Fizik | %20 | FixedUpdate doğru mu? Fall multiplier var mı? |
| 📷 Kamera | %15 | Smooth follow? LateUpdate? |
| ✨ Juice | %10 | Screen shake, hit-stop, partikül? |

### 📊 Birleşik Puanlama Sistemi (Unified Scoring)

Birden fazla ajanın bağımsız değerlendirmelerini **tek bir skora** dönüştüren ağırlıklı ortalama:

```
Final Skor = (Teknik Denetim × 0.60) + (Oyun Hissiyatı × 0.40)
```

- **0-10 arası** tek ve net bir kalite puanı
- Skor **8.0** altındaysa Expert ajan kodu **otomatik olarak yeniden yazar** (Reflexive Loop)
- **Score Clamping:** Tüm skorlar 0-10 aralığına zorlanır (negatif/aşırı skor koruması)

### 🖥️ IDE Benzeri Kullanıcı Arayüzü

- **3 panel layout** — Dosya Gezgini | Kod Editörü | AI Chat
- **Pitch Black** tema — koyu, premium tasarım
- **Syntax highlighting** — C# kod renklendirme
- **Markdown render** — AI yanıtlarında zengin format, emoji ve skor badge'leri
- **Dosya sürükle-bırak** — `.cs` dosyalarını direkt editöre bırak

### 🏗️ Workspace Sistemi

- **Login → Workspace Seç → Uygulama** akışı
- Son açılan workspace'i otomatik hatırlar
- Dosya okuma/yazma desteği (workspace içinde)

### 🤖 Çoklu AI Sağlayıcı Desteği

| Sağlayıcı | Tür | Kullanım | Modeller |
|-----------|-----|----------|----------|
| **Anthropic Claude** | ☁️ Bulut | Multi-Agent Pipeline (Tier 2) | Claude 4.6 Sonnet, Claude 4.6 Opus |
| **OpenAI** | ☁️ Bulut | Direkt OpenAI API | GPT-5.4, GPT-5.4-mini, GPT-5.4-nano |
| **OpenRouter** | ☁️ Bulut | 200+ model erişimi | Kimi 2.5, GPT-5.4, Claude, Gemini vb. |
| **Groq** | ☁️ Bulut | Hızlı tek-ajan analiz (Tier 1) | Llama, Mixtral |
| **Google Gemini** | ☁️ Bulut | Alternatif bulut sağlayıcı | Gemini Pro, Gemini Ultra |
| **DeepSeek** | ☁️ Bulut | OpenAI uyumlu API | DeepSeek Coder |
| **Ollama** | 🖥️ Yerel | Yerel model desteği | Herhangi bir yerel model |



### 🔐 OAuth ile Giriş

Google ve GitHub hesaplarıyla hızlı giriş desteği:

| Sağlayıcı | Durum |
|-----------|-------|
| **Google** | ✅ OAuth 2.0 |
| **GitHub** | ✅ OAuth 2.0 |
| **Kullanıcı Adı/Şifre** | ✅ Klasik kayıt/giriş |

### 🔎 Statik Analiz — Otomatik Tespit Edilen Sorunlar

<details>
<summary><b>Performans</b></summary>

- `GetComponent<T>()` her karede çağrılması
- `GameObject.Find()` / `FindObjectOfType()` Update içinde
- `Camera.main` tekrarlı erişim
- Her karede string birleştirme
- `Input.GetKeyDown()` FixedUpdate içinde

</details>

<details>
<summary><b>Fizik</b></summary>

- Rigidbody varken `transform.position` ile hareket
- Rigidbody varken `transform.Translate` kullanımı

</details>

<details>
<summary><b>Best Practice</b></summary>

- `tag ==` yerine `CompareTag()` kullanılmaması
- Public field'ler — `[SerializeField] private` önerisi
- Sık `Destroy` çağrısı — Object Pooling önerisi

</details>

---

## 🤖 Multi-Agent Mimarisi

Sistem, her biri belirli bir uzmanlık alanına sahip **8 bağımsız ajan** kullanır:

### Analiz Pipeline Ajanları

| Ajan | Rol | Çıktı |
|------|-----|-------|
| 🎯 **Intent Classifier** | Kullanıcı niyetini algılar | `GREETING`, `GENERATION`, `ANALYSIS`, `CHAT` |
| 📋 **Orchestrator** | Mimari düzeltme planı çıkarır | Kısa teknik harita (max 100 kelime) |
| 🔧 **Unity Expert** | Plana göre kodu düzeltir/yeniden yazar | Temiz, Enterprise-level C# kodu |
| ⚖️ **Critic** | Düzeltilmiş kodu denetler ve puanlar | JSON: `{score, review_message, fatal_errors_found}` |
| 🎮 **Game Feel** | Oyun hissiyatını değerlendirir | JSON: `{game_feel_score, movement, combat, physics, ...}` |

### Kod Üretim Pipeline Ajanları

| Ajan | Rol | Çıktı |
|------|-----|-------|
| 🚦 **Clarification Gate** | Muğlak isteklerde eksik bilgileri tespit eder | Maksimum 4 soru veya "geç" kararı |
| 🏗️ **Architect** | Sıfırdan mimari plan oluşturur | Kısa tasarım blueprint'i (ADIM 0→3 scope garantisi) |
| 💻 **Coder** | Plana göre sıfırdan kod üretir | Tam çalışan C# kodu |

### Ajan Güvenlik Mekanizmaları

```
┌─────────────────────────────────────────────────────┐
│              AGENT CONSTRAINT SYSTEM                │
├─────────────────────────────────────────────────────┤
│ ✅ max_tokens Limitleri:                            │
│    • Critic: 1024 token (kısa ve öz)               │
│    • Game Feel: 1500 token                          │
│    • Coder: 8192 token (tam mimari üretimi)         │
│                                                     │
│ ✅ Negatif Kısıtlamalar (Rol Sapması Engeli):       │
│    • Critic: "ASLA kod yazma"                       │
│    • Game Feel: "ASLA kod bloğu üretme"             │
│                                                     │
│ ✅ Post-Processing:                                 │
│    • Code block stripping (Critic yanıtlarından)    │
│    • Score clamping (0-10 arası zorlama)             │
│    • JSON temizleme ve kurtarma (Validator)          │
└─────────────────────────────────────────────────────┘
```

---

## ⚙️ Pipeline Sistemi

### 🔍 Tier 1 — Tek Ajan Analizi (Groq, Ollama, Gemini)

```
Kullanıcı Kodu → Statik Analiz → AI Analiz → Kod Düzeltme → Sonuç
```

Hızlı ve basit; tek bir LLM çağrısıyla analiz-düzeltme yapar.

### 🔗 Tier 2 — Multi-Agent Analiz (Claude)

```
                    ┌─────────────┐
                    │ Orchestrator│ Plan oluşturur
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
              ┌────►│   Expert    │ Kodu düzeltir
              │     └──────┬──────┘
              │            │
              │     ┌──────▼──────────────────┐
              │     │    asyncio.gather()      │ ← Paralel çalışır
              │     │  ┌────────┐ ┌──────────┐ │
              │     │  │ Critic │ │Game Feel │ │
              │     │  │(1024t) │ │ (1500t)  │ │
              │     │  └───┬────┘ └────┬─────┘ │
              │     └──────┼───────────┼───────┘
              │            │           │
              │     ┌──────▼───────────▼──────┐
              │     │  Unified Score (0-10)    │
              │     │  Tech×0.6 + GameFeel×0.4 │
              │     └──────────┬───────────────┘
              │                │
              │        Score < 8.0?
              │           YES │ NO
              └───────────────┘  │
                                 ▼
                          ✅ Final Rapor
```

- **Reflexive Loop:** Skor 8.0 altındaysa Expert kodu otomatik yeniden yazar (max 2 deneme)
- **Combined Feedback:** Retry sırasında hem teknik hem oyun hissiyatı eleştirisi birlikte gönderilir

### 🆕 Tier 3 — Sıfırdan Kod Üretim Pipeline (Multi-Agent, sadece Claude)

```
Kullanıcı İsteği
      │
      ▼
Clarification Gate ──── Muğlak? ──► Soru Sor (max 4) ──► Kullanıcı Cevaplar
      │ Yeterince Spesifik                                         │
      │◄────────────────────────────────────────────────────────────┘
      ▼
  Architect
  ┌─────────────────────────────────────────────────┐
  │ ADIM 0: Kullanıcının tüm isteklerini listele    │
  │ ADIM 1-2: Mimari plan (Bölüm A + Bölüm B)      │
  │ ADIM 3: Scope doğrulama (her istek ✅ olmalı)  │
  └─────────────────┬───────────────────────────────┘
                    │ Dosya listesi (örn: 23 dosya)
                    ▼
              Batch Splitter
              (BATCH_SIZE = 10)
         ┌────────┬────────┐
         ▼        ▼        ▼
      Batch 1  Batch 2  Batch 3
      (10 dos) (10 dos) (3 dos)
         │        │        │
         └────────┴────────┘
                  │ her batch → Coder
                  ▼
               Coder
          (max 8192 token)
                  │
                  ▼
         Game Feel Loop
    (sessiz denetim, düşük skorsa yeniden yaz)
                  │
                  ▼
           ✅ Final Kod
```

- **Clarification Gate:** Kullanıcı muğlak istek yaptıysa önce soru sorar (max 4 soru, tek mesajda). Cevap verildikten sonra bir daha sormaz — `skip_gate` mekanizmasıyla atlar.
- **Architect Scope Garantisi:** ADIM 0'da tüm kullanıcı istekleri numaralandırılır. ADIM 3'te her istek için ✅/❌ doğrulaması yapılır. ❌ olan özellik varsa Architect kendi planına geri döner ve ekler.
- **Batch Splitting:** Büyük sistemler (örn. 23 dosyalık RPG) 10'ar dosyalık batch'lere bölünür. Her batch ayrı Coder çağrısıyla üretilir. Kullanıcı "devam et" yazarak sonraki batch'i başlatır.
- **Continuation State:** Batch durumu sunucunun `continuation_store`'unda saklanır; kullanıcı "devam et / evet / tamam" yazınca otomatik algılanır.

### 🆕 Tier 4 — SingleAgent Kod Üretim Pipeline (Tüm sağlayıcılar)

```
Kullanıcı İsteği → Tek AI Çağrısı (Plan + Kod + Game Feel kuralları gömülü) → Final Kod
                                        │
                              Token limitinde kesildi?
                                   YES │ NO
                                       │    ▼
                              Açık ``` ▼  Sonuç
                              kapatılır + "devam et" mesajı
```

- Claude dışındaki tüm sağlayıcılar (OpenAI, OpenRouter, Groq, Gemini, DeepSeek, Ollama) bu pipeline'ı kullanır
- Sağlayıcıya özel token limitleri: Google 65K, Groq 32K, diğerleri 16K
- İngilizce prompt ile daha iyi LLM çıktı kalitesi
- Game Feel kuralları, Save/Load kuralları ve output format doğrudan prompt'a gömülü
- Token kesintisinde yanıt otomatik kapatılır, kullanıcı "devam et" ile devam edebilir
- **Groq Free Tier:** 413/token-limit hatası geldiğinde teknik API mesajı yerine kullanıcı dostu hata gösterilir

---

## 🏛️ Mimari (Genel Bakış)

```
┌─────────────────────────────────────────────────────────────┐
│                    ELECTRON (Nextron)                        │
│  ┌──────────┐  ┌─────────────────┐  ┌────────────────────┐ │
│  │ Dosya    │  │   Kod Editörü   │  │   AI Chat          │ │
│  │ Gezgini  │  │   (Syntax HL)   │  │   (Markdown)       │ │
│  │          │  │                 │  │   Score Badge      │ │
│  │ .cs      │  │  C# highlight  │  │   Game Feel UI     │ │
│  │ files    │  │                 │  │   Skor Grafiği     │ │
│  └──────────┘  └─────────────────┘  └───────┬────────────┘ │
│                                              │              │
└──────────────────────────────────────────────┼──────────────┘
                                               │ HTTP (REST)
┌──────────────────────────────────────────────┼──────────────┐
│              PYTHON BACKEND (FastAPI)         │              │
│                                               │              │
│  ┌──────────────┐   ┌────────────────────────▼───────────┐  │
│  │ Intent       │   │         Pipeline Router            │  │
│  │ Classifier   │──▶│  GREETING → Direkt Yanıt           │  │
│  │ (LLM+Regex)  │   │  ANALYSIS → Multi-Agent Pipeline   │  │
│  └──────────────┘   │  GENERATION → Code Gen Pipeline    │  │
│                      │  CHAT → Genel Sohbet               │  │
│                      └───────────────┬───────────────────┘  │
│                                      │                      │
│  ┌────────────┐  ┌──────────┐  ┌─────▼──────┐              │
│  │ Statik     │  │ Report   │  │ Agent Team │              │
│  │ Analyzer   │  │ Engine   │  │ (8 Ajan)   │              │
│  │ (regex)    │  │ (skor)   │  │            │              │
│  └────────────┘  └──────────┘  └─────┬──────┘              │
│                                      │                      │
│  ┌───────────────┐  ┌────────┐  ┌────▼───────────────────┐ │
│  │ AI Providers  │  │ SQLite │  │ Validator + Sanitizer  │ │
│  │ (6 sağlayıcı) │  │  DB    │  │ (JSON clean, clamp)   │ │
│  └───────────────┘  └────────┘  └────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔐 Güvenlik Mimarisi

### IPC Kanal Whitelist

Electron'da renderer process ile main process arasındaki tüm `invoke` çağrıları sabit bir whitelist üzerinden geçer. Liste dışındaki her kanal `Promise.reject` ile anında reddedilir:

```typescript
// main/helpers/ipc-whitelist.ts
export const ALLOWED_INVOKE_CHANNELS = new Set([
  'open-file-dialog', 'open-folder-dialog',
  'read-directory', 'read-file',
  'write-file', 'file-exists', 'write-multiple-files',
  'session-get', 'session-set', 'session-clear',
  'get-backend-base-url',
])
```

IPC testleri (`__tests__/ipc-whitelist.test.ts`) gerçek `ipc-whitelist.ts` dosyasını import eder — kaynak dosya bozulursa testler de fail eder.

### Dosya Sistemi Koruması

Tüm dosya işlemleri `path.resolve()` + `path.relative()` ile path traversal saldırılarına karşı korunur:

| Handler | Kısıt |
|---------|-------|
| `read-directory` | Yalnızca workspace dizini içi |
| `read-file` | Workspace içi + yalnızca `.cs` |
| `write-file` / `write-multiple-files` | `workspace/Assets/Scripts/**/*.cs` |
| `file-exists` | `workspace/Assets/Scripts/**/*.cs` |

```typescript
// Örnekler — bunların hepsi false döner
isAllowedWorkspaceReadFile('/etc/passwd', workspace)
isAllowedUnityScriptPath('../../../secrets.cs', workspace)
isAllowedUnityScriptPath('/tmp/exploit.cs', workspace)
```

### Session Token Güvenliği — `safeStorage`

Session token artık `localStorage`'da değil, OS'un şifreli deposunda saklanır:

- **Windows** → DPAPI (Data Protection API)
- **macOS** → Keychain

`session.enc` dosyası `app.getPath('userData')` altında şifreli olarak durur. Mevcut `localStorage` token'ları ilk açılışta otomatik olarak `safeStorage`'a taşınır.

`safeStorage` kullanılamıyorsa (headless ortam vb.) kullanıcıya açıkça uyarı gösterilir — sessiz persistence kaybı olmaz.

### API Key At-Rest Şifrelemesi

Kullanıcıların AI provider API key'leri SQLite'ta Fernet ile şifreli saklanır. Şifreleme anahtarı OS keystore'da tutulur (veritabanıyla aynı dizinde değil):

```
Öncelik sırası:
1. API_KEY_ENCRYPTION_KEY env var
2. Windows Credential Manager / macOS Keychain  (keyring)
3. Fallback: ~/.unity_architect_ai/api_key_fernet.key
```

Mevcut kurulumlar ilk açılışta otomatik olarak keystore'a migrate edilir.

Kullanıcı parolaları bcrypt ile hash'lenir — geri çözülmez.

### Rate Limiting — Sliding Window

Brute-force ve credential stuffing saldırılarına karşı IP bazlı sliding window:

| Endpoint | Limit | Pencere |
|----------|-------|---------|
| `POST /login` | 5 deneme | 5 dakika |
| `POST /auth/complete/{code}` | 10 deneme | 1 dakika |

Başarılı girişte sayaç sıfırlanır — meşru kullanıcılar bloke kalmaz.

### Backend Port Güvenliği

Backend sabit port 8000'de değil, başlangıçta `net.createServer({ port: 0 })` ile OS'tan rastgele bir port alır. Port, renderer'a yalnızca `get-backend-base-url` IPC kanalıyla iletilir — renderer URL'yi kendisi belirleyemez.

### OAuth Güvenliği

- Tüm OAuth callback'leri PKCE yerine `state` token doğrulamasıyla CSRF'e karşı korunur
- `postMessage` yalnızca bilinen `localhost` ve `app://` origin'lerine gönderilir
- OAuth callback completion code'ları tek kullanımlıktır (`consume_oauth_completion`)
- Build'e `.env` dahil edilmez — OAuth kimlik bilgisi yoksa butonlar otomatik gizlenir

### Test Kapsamı

| Dosya | Test Sayısı | Kapsam |
|-------|-------------|--------|
| `ipc-whitelist.test.ts` | 23 | Whitelist doğruluğu, injection denemeleri, case bypass |
| `file-security.test.ts` | 20 | Path traversal, workspace sınırı, extension kontrolü |
| `session-storage.test.ts` | 20 | Round-trip, migration, şifreleme yoksa fallback |
| `regression-ipc.test.ts` | 18 | background.ts ↔ preload senkronizasyonu |
| `toast.test.ts` | 19 | Hook mantığı, auto-dismiss, tip doğruluğu |
| `test_auth_rate_limit.py` | 8 | Rate limit entegrasyon testleri (FastAPI TestClient) |

---

## 🛠️ Geliştirme Hikayeleri & Alınan Dersler

Projeyi geliştirirken karşılaşılan gerçek problemler ve çözümleri:

---

### 1. "Tek Claude çok pahalı" — Neden 2-Ajan Mimarisine Geçtik?

İlk tasarımda sıfırdan kod üretimi için tek bir Claude çağrısı kullanılıyordu: tüm kod tek seferde, tek prompt'ta. Basit sistemler için yeterliydi ama karmaşık isteklerde (RPG, survival, inventory+crafting+quest birlikte) problem ortaya çıktı:

- **Token maliyeti:** Tek çağrıda hem planlama hem kodlama hem de game feel denetimi yapmak, her seferinde çok büyük ve pahalı bir prompt anlamına geliyordu.
- **Kalite tutarsızlığı:** AI bazen planlamaya, bazen kodlamaya odaklanıyor; ikisini aynı anda iyi yapamıyordu.

**Çözüm:** Sorumlulukları ayırdım. **Architect** yani Claude sadece plan yapar (hafif, hızlı, ucuz), **Coder** yani Chatgpt sadece kod yazar (yoğun, odaklı). İki küçük uzman çağrısı, bir büyük generalist çağrısından hem daha ucuz hem daha kaliteli çıktı verdi.

---

### 2. Architect 7 Özellikten Sadece 3'ünü Planlıyordu

Gerçek bir kullanıcı testi: RPG için şu 7 özellik istendi — hareket, savaş, düşman AI, **envanter, ekipman, görev sistemi, save/load**. Architect planına bakınca sadece hareket, savaş ve AI vardı. 4 özellik yok.

**Neden oluyordu?** Architect prompt'unda "kullanıcının isteklerini karşıla" diyordu ama hangi isteklerin karşılanıp karşılanmadığını doğrulayan bir mekanizma yoktu. AI büyük scope'ta önce aklına gelenleri planlıyor, geri kalanları unutuyordu.

**Çözüm: ADIM 0 + ADIM 3**

```
ADIM 0: Kullanıcının mesajındaki her isteği numaralandırdım.
  İSTEK-1: envanter sistemi
  İSTEK-2: ekipman
  ...
  TOPLAM: 7 istek

ADIM 3: Her istek için kontrol ettirdim.
  ✅ İSTEK-1: envanter → InventoryManager.cs
  ❌ İSTEK-2: ekipman → DOSYA YOK → hemen ADIM 2'ye ekle
```

Artık Architect kendi planını kendi doğruluyor. ❌ bulursa düzeltmeden devam edemiyor.

---

### 3. Clarification Gate İki Kez Soru Soruyordu

Kullanıcı muğlak bir istek yaptığında Gate soru soruyordu. Kullanıcı cevap verince Gate **tekrar** soru soruyordu — sanki ilk konuşmayı hiç görmemiş gibi.

**Neden?** `context_summary` sadece 200 karakter tutuluyordu. Cevap verildiğinde Gate, orijinal prompt + soruları göremiyordu, her şeyi yeniden değerlendirip tekrar soru soruyordu.

**Çözüm 1:** `context_summary` limitini 800 karaktere çıkardım.
**Çözüm 2:** Son assistant mesajında soru işareti var mı? Varsa `skip_gate = True` geç, doğrudan Architect'e gönder. 
**Çözüm 3:** `_combined_prompt` — orijinal istek + kullanıcının cevapları birleştirilerek Architect'e gönderilir. Böylece Architect kısa cevapları değil, tam bağlamı görür.

---

### 4. "Devam Et" Yanlış Hata Veriyordu

Single agent token limitinde kesildiğinde kullanıcı "devam et" yazıyordu. Ama sistem "aktif bir batch oturumu yok" hatası veriyordu.

**Neden?** Multi-agent batch sistemi `continuation_store`'u doldurur. Single agent ise doldurmaz — token kesintisi onun mekanizması değil. Ama "devam et" mesajını dinleyen guard ikisini ayırt etmiyordu.

**Çözüm:** Guard'a ekstra kontrol: son assistant mesajı "Token limitine ulaşıldı" içeriyor mu? İçeriyorsa single agent kesintisidir, `no_state_msg` gösterme, normal konuşma olarak devam et.

---

### 5. Save Sistemi PlayerPrefs Kullanıyordu

Single agent ile üretilen RPG kodlarında SaveSystem her seferinde `PlayerPrefs` ile veri kaydediyordu. Bu Unity'de küçük, geçici veriler için kabul edilebilir ama save/load sistemi için yanlış — büyük veri, binary olmayan yapı, platform kısıtlamaları.

**Çözüm:** Single agent prompt'una `[SAVE/LOAD RULES]` bölümü ekledim:
```
- JSON dosyası kullan: Application.persistentDataPath + "/save.json"
- ASLA PlayerPrefs kullanma (kullanıcı açıkça istemediği sürece)
- JsonUtility.ToJson / FromJson + File.WriteAllText / ReadAllText
```

Sonraki üretimlerde SaveManager doğru JSON implementasyonuyla geliyor.

---

### 6. Büyük Sistemlerde Token Limiti — Batch Sistemi

23 dosyalık RPG sistemi tek Coder çağrısına sığmıyor. 8192 token limitinde yarım kod, açık süslü parantez, syntax hatası çıkıyor.

**Çözüm:** Architect planındaki dosya listesini parse etttim, 10'arlı gruplara böldüm. Her grup ayrı Coder çağrısı. Kullanıcıya "Batch 1/3 tamamlandı, devam edeyim mi?" göster. Durum `continuation_store`'da saklanır, kullanıcı "devam et" deyince bir sonraki batch başlar.

Gerçek test: 23 dosyalık tam RPG sistemi (PlayerController, EnemyAI, InventoryManager, CraftingManager, QuestManager, SaveManager dahil) 3 batch'te eksiksiz üretildi.

---

## 🚀 Kurulum

### Gereksinimler

| Gereksinim | Sürüm | Not |
|------------|-------|-----|
| **Python** | **3.13** | 3.14 desteklenmez — `grpcio` wheel yok |
| **Node.js** | 18+ | |
| **npm** | 9+ | Node.js ile birlikte gelir |

> **Önemli:** Python **3.13** kullanın. Python 3.14, `grpcio` paketinin henüz wheel (ön derlenmiş binary) yayınlamaması nedeniyle `pip install` aşamasında hata verir.

### 1. Repoyu Klonla

```bash
git clone https://github.com/BurakErdemci/Unity-Architect-AI.git
cd Unity-Architect-AI
```

### 2. Backend Kurulumu

#### Python 3.13 kurulumu (sisteminizde yoksa)

**macOS:**
```bash
brew install python@3.13
```

**Windows:**
```powershell
winget install Python.Python.3.13
# Kurulumdan sonra terminali yeniden başlat
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt install python3.13 python3.13-venv
```

---

#### Sanal ortam (venv) oluşturma

**macOS / Linux:**
```bash
cd Backend
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell):**
```powershell
cd Backend
py -3.13 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

> **`py -3.13` neden?** Windows'ta birden fazla Python sürümü yüklüyse `python` komutu hangi sürümü kullanacağını bilemez. `py -3.13` Python Launcher aracılığıyla tam olarak 3.13 sürümünü hedefler.

---

#### .env dosyası oluştur

`Backend/.env` dosyası oluştur. Google veya GitHub OAuth kullanmayacaksan içini boş bırakabilirsin:

**macOS / Linux:**
```bash
cat > .env << EOF
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret
EOF
```

**Windows** — `.env` dosyasını metin editörüyle oluşturup içine yaz:
```env
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret
```

> **Not:** Bu değişkenler yalnızca Google/GitHub OAuth girişi içindir. Anthropic, OpenAI, Gemini gibi AI API anahtarları buraya yazılmaz. Bunlar uygulama içindeki Ayarlar ekranından girilir ve işletim sisteminin güvenli deposunda (Keychain / Windows Credential Manager) şifreli saklanır.

---

#### Venv sorun giderme

**`grpcio` veya `protobuf` kurulumu başarısız oluyorsa**

Büyük ihtimalle Python 3.14 kullanılıyordur. Önce sürümü kontrol et:

```bash
python --version
# Windows'ta kurulu sürümleri listele:
py --list
```

3.14 çıkıyorsa Python 3.13'ü kur, sonra eski venv'i silip yeniden oluştur:

macOS / Linux:
```bash
rm -rf venv
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell):
```powershell
Remove-Item -Recurse -Force venv
py -3.13 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

> Windows'ta `rm -rf` **PowerShell'de çalışmaz**. `Remove-Item -Recurse -Force` kullan veya Git Bash / WSL aç.

---

**`pip` paket çakışması — `google-api-core` vs `grpcio-status`**

Şuna benzer bir hata çıkıyorsa:
```
ERROR: pip's dependency resolver does not currently take into account all the packages...
```

`pip`'i güncelleyip tekrar dene:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

**`venv\Scripts\activate` çalışmıyor (Windows)**

PowerShell script çalıştırma politikası kısıtlı olabilir. Bir kereliğine şunu çalıştır:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
Sonra tekrar `venv\Scripts\activate` dene.

---

### 3. Frontend Kurulumu

```bash
cd Frontend/frontend
npm install

# Uygulamayı başlat (Electron + Next.js)
# Backend venv aktifse otomatik başlatılır, ayrıca uvicorn çalıştırmana gerek yok
npm run dev
```

Uygulama otomatik olarak açılacaktır.

> **Not:** `npm run dev` çalıştırıldığında Electron, `Backend/venv/Scripts/python` (Windows) veya `Backend/venv/bin/python` (macOS/Linux) ile backend'i otomatik başlatır.
>
> **Kayıt ekranında şifre en az 8 karakter olmalıdır.**

### 4. Docker ile Kurulum (Önerilen — Python kurulumu gerekmez)

Docker kullanarak backend'i Python kurmadan çalıştırabilirsin. Bu yöntemde sadece **Docker Desktop** ve **Node.js** yeterlidir.

> **Not:** Anthropic, OpenAI, Groq gibi AI API anahtarları `.env` dosyasına yazılmaz. Bunlar uygulama içindeki Ayarlar ekranından girilir ve işletim sisteminin güvenli anahtar deposunda (Keychain/Credential Manager) şifreli olarak saklanır.

#### Gereksinimler

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/macOS/Linux)
- Node.js 18+

#### Adım 1 — `.env` dosyasını oluştur

`Backend/.env` dosyası oluştur. Google veya GitHub ile giriş kullanmayacaksan bu dosyayı boş bırakabilirsin. OAuth kullanacaksan ilgili alanları doldur:

```env
# Google ile giriş kullanmak istersen:
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret

# GitHub ile giriş kullanmak istersen:
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret
```

#### Adım 2 — Docker backend'i başlat

```bash
# Projenin kök dizininde
docker compose up --build -d
```

İlk çalıştırmada bağımlılıklar indirilir (~1-2 dakika). Sonraki başlatmalarda çok daha hızlıdır.

Backend sağlık kontrolü:

```bash
curl http://127.0.0.1:8000/health
# Beklenen çıktı: {"status":"ok","service":"unity-architect-ai"}
```

#### Adım 3 — Frontend'i kur ve başlat

```bash
cd Frontend/frontend
npm install

# Docker modunda başlat (Python spawn etmez, Docker backend'e bağlanır)
npm run dev:docker
```

#### Docker loglarını izle

```bash
# Gerçek zamanlı log akışı
docker compose logs -f

# Sadece son 50 satır
docker compose logs --tail=50
```

#### Docker'ı durdur

```bash
docker compose down
```

#### Backend kodunu değiştirince yeniden başlatma

Mac/Linux'ta `kill port` + `npm run dev` yaptığın gibi, Docker'da backend kodunu değiştirince şunu çalıştır:

```bash
# Rebuild + yeniden başlat (tek komut)
docker compose up --build -d
```

Bu komut değişen katmanları yeniden derler ve container'ı yeniden başlatır. Çalışan container'ı durdurmana gerek yok, otomatik halleder.

Sadece yeniden başlatmak istiyorsan (kod değişikliği yoksa):

```bash
docker compose restart
```

#### Sorun Giderme

**Build cache bozulması hatası** (`parent snapshot ... does not exist`):
```bash
docker builder prune -f
docker compose up --build -d
```

**Backend porta bağlanamıyor** — Docker Desktop'ın çalıştığından emin ol, sonra:
```bash
docker compose down
docker compose up --build -d
```

> **Not:** Kayıt ekranında şifre en az 8 karakter olmalıdır.

---

## 💡 Kullanım

### Temel Akış

1. **Giriş Yap** — Kullanıcı adı ve şifre ile kayıt ol / giriş yap
2. **Workspace Seç** — Unity projenin `Assets/Scripts` klasörünü seç
3. **Dosya Seç** — Sol panelden bir `.cs` dosyasına tıkla
4. **Analiz Et** — Chat'e "Bu kodu analiz et" yaz veya kodu doğrudan yapıştır
5. **Sıfırdan Üret** — "Bana bir FPS hareket sistemi yaz" gibi bir istek gönder
6. **Sonuçları İncele** — Birleşik skor, teknik denetim ve oyun hissiyatı raporu

### Örnek Kullanım Senaryoları

| Senaryo | Prompt Örneği | Pipeline |
|---------|---------------|----------|
| Mevcut kodu analiz et | Dosyayı seç → "Analiz et" | Multi-Agent |
| Sıfırdan kod üret | "Bana fizik tabanlı zombi takip sistemi yaz" | Code Generation |
| Performans optimizasyonu | "Bu koddaki performans sorunlarını bul" | Multi-Agent |
| Genel Unity sorusu | "Unity'de Object Pooling nasıl yapılır?" | Chat |

---

## 🛠️ Teknoloji Yığını

### Backend
| Teknoloji | Kullanım |
|-----------|----------|
| **Python 3.9+** | Ana backend dili |
| **FastAPI** | REST API framework |
| **SQLite / SQLAlchemy** | Kullanıcı verileri, sohbet geçmişi, workspace |
| **Uvicorn** | ASGI sunucu |
| **Anthropic SDK** | Claude API entegrasyonu |
| **Groq SDK** | Groq API entegrasyonu |
| **google-generativeai** | Gemini API entegrasyonu |
| **Ollama** | Yerel AI model yönetimi |
| **passlib + bcrypt** | Şifre hash'leme |

### Frontend
| Teknoloji | Kullanım |
|-----------|----------|
| **Electron 34** | Masaüstü uygulama çerçevesi |
| **Next.js 14** | React framework |
| **React 18** | UI bileşenleri |
| **Tailwind CSS** | Pitch Black tema & stil sistemi |
| **Framer Motion** | Premium animasyonlar |
| **react-markdown** | AI yanıtlarında Markdown render |
| **react-syntax-highlighter** | C# kod renklendirme |
| **Lucide React** | İkon kütüphanesi |

### Araçlar
| Araç | Kullanım |
|------|----------|
| **Nextron** | Electron + Next.js entegrasyonu |
| **electron-builder** | Uygulama paketleme (exe/dmg) |
| **Axios** | HTTP istemci |
| **unittest** | Python test framework |

---

## 📁 Proje Yapısı

```
Unity-Architect-AI/
├── Backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI uygulama + endpointler + timeout yönetimi
│   │   ├── ai_providers.py          # 6 AI sağlayıcı (max_tokens destekli)
│   │   ├── analyzer.py              # Statik kod analiz motoru (regex)
│   │   ├── database.py              # SQLite veritabanı yönetimi
│   │   ├── prompts.py               # Prompt şablonları ve Unity kuralları
│   │   ├── report_engine.py         # Ağırlıklı puanlama sistemi
│   │   ├── validator.py             # JSON temizleme, score clamping, yanıt doğrulama
│   │   │
│   │   └── pipelines/
│   │       ├── base.py                    # Pipeline temel sınıfları
│   │       ├── single_agent_pipeline.py   # Tier 1: Tek ajan analiz
│   │       ├── multi_agent_pipeline.py    # Tier 2: Multi-Agent + Reflexive Loop
│   │       ├── code_generation_pipeline.py # Tier 3: Sıfırdan kod üretimi
│   │       │
│   │       └── agents/
│   │           ├── intent_classifier.py   # 🎯 Niyet algılama (LLM + Regex)
│   │           ├── orchestrator.py        # 📋 Düzeltme planı oluşturucu
│   │           ├── unity_expert.py        # 🔧 Kod düzeltici (Coder)
│   │           ├── critic.py              # ⚖️ Teknik denetçi (max 1024t)
│   │           ├── game_feel_agent.py     # 🎮 Oyun hissiyatı analisti
│   │           ├── architect_generation.py # 🏗️ Sıfırdan mimari planlayıcı
│   │           └── coder_generation.py    # 💻 Sıfırdan kod üretici (max 8192t)
│   │
│   ├── tests/
│   │   └── test_validator.py        # Validator unit testleri (12 test)
│   ├── requirements.txt
│   ├── Dockerfile                   # Backend Docker imajı
│   ├── .dockerignore
│   └── .env                         # API anahtarları (git'e eklenmez)
│
├── Frontend/
│   └── frontend/
│       ├── main/
│       │   ├── background.ts        # Electron ana süreç + Backend auto-start
│       │   └── preload.ts           # IPC köprüsü (dosya sistemi)
│       ├── renderer/
│       │   ├── pages/
│       │   │   └── home.tsx         # Ana uygulama bileşeni (3-panel layout)
│       │   ├── components/          # UI bileşenleri
│       │   └── styles/
│       │       └── globals.css      # Pitch Black tema
│       ├── package.json
│       ├── nextron.config.js
│       └── electron-builder.yml
│
├── docker-compose.yml              # Docker ile backend başlatma
├── .env.example                    # Örnek environment değişkenleri
├── .gitignore
└── README.md
```

---

## 📡 API Dokümantasyonu

Backend çalışırken: [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger UI)

### Ana Endpointler

| Metod | Endpoint | Açıklama |
|-------|----------|----------|
| `POST` | `/register` | Yeni kullanıcı kaydı |
| `POST` | `/login` | Kullanıcı girişi |
| `POST` | `/chat` | AI ile sohbet (pipeline aktif, 300s timeout) |
| `POST` | `/analyze` | Statik kod analizi |
| `POST` | `/save-ai-config` | AI sağlayıcı ve model ayarlarını kaydet |
| `GET` | `/available-models` | Mevcut AI modellerini listele (Ollama + Bulut) |
| `POST` | `/conversations` | Yeni sohbet oluştur |
| `GET` | `/conversations/{user_id}` | Kullanıcının sohbetleri |
| `DELETE` | `/conversations/{conv_id}` | Sohbet silme |
| `POST` | `/save-workspace` | Workspace yolunu kaydet |
| `GET` | `/last-workspace/{user_id}` | Son workspace yolunu getir |
| `POST` | `/write-file` | Dosya yaz (workspace içinde) |
| `GET` | `/auth/google/url` | Google OAuth başlatma URL'i |
| `GET` | `/auth/google/callback` | Google OAuth callback |
| `GET` | `/auth/github/url` | GitHub OAuth başlatma URL'i |
| `GET` | `/auth/github/callback` | GitHub OAuth callback |

---

## 🗺️ Yol Haritası

### ✅ Tamamlanan (Sprint 1 & 2.1)

- [x] IDE benzeri 3 panel arayüz (Pitch Black tema)
- [x] Çoklu AI sağlayıcı desteği (Claude, Groq, Gemini, Ollama, OpenAI, DeepSeek)
- [x] Statik kod analiz motoru (Unity C# regex kuralları)
- [x] Multi-Agent Analiz Pipeline (Orchestrator → Expert → Critic → Game Feel)
- [x] Sıfırdan Kod Üretim Pipeline (Architect → Coder → Game Feel Loop)
- [x] LLM tabanlı Intent Classifier (Niyet Algılama)
- [x] Oyun Hissiyatı (Game Feel) Ajan Entegrasyonu
- [x] Birleşik Puanlama Sistemi (Teknik %60 + Oyun Hissiyatı %40)
- [x] Reflexive Loop (Skor düşükse otomatik yeniden yazma)
- [x] Agent Hardening (max_tokens, negatif kısıtlamalar, post-processing)
- [x] Pipeline Performans Optimizasyonu (paralel ajan çalışması)
- [x] JSON Robustness (temizleme, kurtarma, score clamping)
- [x] Workspace yönetim sistemi
- [x] Sohbet sistemi (çoklu konuşma, geçmiş)
- [x] Unit testler (Validator)

### ✅ Tamamlanan (Sprint 2.2)

- [x] OpenRouter entegrasyonu (200+ model erişimi)
- [x] OpenAI direkt API desteği (GPT-5.4 model ailesi)
- [x] SingleAgent Code Generation Pipeline (Claude dışı sağlayıcılar)
- [x] Google & GitHub OAuth ile giriş
- [x] Docker desteği (Dockerfile + docker-compose)
- [x] Production build (Electron + Backend bundled)
- [x] Backend auto-start (build'de otomatik başlatma)

### ✅ Tamamlanan (Sprint 2.3)

- [x] Clarification Gate — muğlak isteklerde soru-cevap akışı, bir kez sorar
- [x] Architect ADIM 0 + ADIM 3 — scope garantisi, hiçbir kullanıcı isteği atlanamaz
- [x] Batch Splitting (BATCH_SIZE=10) — 23+ dosyalık büyük sistemler 10'ar dosyalık batch'lerde üretilir
- [x] `continuation_store` — batch durumu hafızada, "devam et" ile sonraki batch
- [x] skip_gate mekanizması — clarification cevabı verildikten sonra Gate'i atla
- [x] combined_prompt — orijinal istek + cevaplar birleştirilerek Architect'e gönderilir
- [x] Single Agent token kesinti fix — "devam et" artık yanlış hata vermiyor
- [x] Single Agent Save/Load kuralları — PlayerPrefs yerine JSON dosyası zorunlu
- [x] Groq free tier hata mesajı — 413/token-limit hatası kullanıcı dostu mesaja dönüştürülür

### ✅ Tamamlanan (Sprint 2.4 — Güvenlik Sertleştirme)

- [x] IPC kanal whitelist — renderer'dan yalnızca izinli kanallar çağrılabilir
- [x] Dosya sistemi path traversal koruması — `workspace/Assets/Scripts/*.cs` sınırı
- [x] Session token `safeStorage`'a taşındı — Windows DPAPI / macOS Keychain
- [x] `localStorage → safeStorage` otomatik migration
- [x] API key şifreleme anahtarı OS keystore'a taşındı (keyring)
- [x] Rate limiting — `/login` (5/5dk) ve `/auth/complete` (10/60sn)
- [x] OAuth `app://` origin fix — production Electron'da OAuth akışı artık çalışıyor
- [x] Backend dinamik port — hardcode 8000 kaldırıldı
- [x] `.env` build'e dahil edilmiyor — OAuth kimlik bilgisi yoksa butonlar gizleniyor
- [x] PyInstaller entegrasyonu — hedef makinede Python kurulu olmasına gerek yok
- [x] Backend başlatma hatası kalıcı hata ekranı — sessiz başarısızlık ortadan kalktı
- [x] 108 frontend unit testi (Vitest) + 8 backend entegrasyon testi

### ✅ Tamamlanan (Sprint 3)

- [x] Built-in Unity Expert (Yerel bilgi bankası + offline destek)
- [x] Genişletilmiş Statik Analiz kuralları

### 📋 Planlanan

- [ ] Code Memory Snapshot — önceki üretilen dosyaları SQLite'ta özet olarak sakla, modifikasyon isteklerinde akıllı context injection
- [ ] Dashboard ve analiz grafikleri
- [ ] PDF rapor dışa aktarma
- [ ] Geri bildirim öğrenme sistemi (kullanıcı feedback → kural iyileştirme)

---

## 👨‍💻 Geliştirici

**Burak Emre Erdemci**

---

## 📄 Lisans

Bu proje [MIT Lisansı](LICENSE) ile lisanslanmıştır.
