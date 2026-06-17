<div align="center">

# Unity Architect AI

**Unity Geliştiricileri için Otonom, Güvenli ve Agentic Yazılım Stüdyosu**

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Electron](https://img.shields.io/badge/Electron-34-47848F?style=for-the-badge&logo=electron&logoColor=white)](https://electronjs.org)
[![React](https://img.shields.io/badge/React-18.3-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.7-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Unity MCP](https://img.shields.io/badge/Unity_MCP-Aktif-7B2FBE?style=for-the-badge&logo=unity&logoColor=white)](./unity-mcp)
[![License](https://img.shields.io/badge/Lisans-MIT-green?style=for-the-badge)](LICENSE)

*Unity Architect AI, sıradan bir kod asistanı değildir. Projenizi baştan sona tanıyan, terminali yöneten, Unity Editor'e doğrudan komut veren ve tüm bunları katmanlı bir güvenlik sistemi arkasında yapan otonom bir geliştirme ortağıdır.*

[English README](./README_EN.md)

</div>

---

## İçindekiler

- [Neden Unity Architect AI?](#-neden-unity-architect-ai)
- [Özellikler](#-özellikler)
- [Sistem Mimarisi](#-sistem-mimarisi)
- [Desteklenen AI Sağlayıcılar](#-desteklenen-ai-sağlayıcılar)
- [Tool Ekosistemi (MCP + Function Calling)](#tool-ekosistemi-mcp--function-calling)
- [Güvenlik Mimarisi](#️-güvenlik-mimarisi)
- [Kurulum](#-kurulum)
- [Kullanım](#-kullanım)
- [Unity MCP Entegrasyonu](#-unity-mcp-entegrasyonu)
- [Agentic Sistem Detayları](#-agentic-sistem-detayları)
- [API Referansı](#-api-referansı)
- [Geliştirici Notları: Alınan Dersler](#geliştirici-notları-alınan-dersler-ve-mimari-kararlar)
- [Katkıda Bulunma](#-katkıda-bulunma)

---

## Neden Unity Architect AI?

Unity ekosisteminde AI araçları iki kategoriden birine düşer: ya sadece kod yazar, ya da sadece sohbet eder. Her ikisi de gerçek bir geliştirme ortağının yapması gerekeni —projeyi anlamak, hatayı bulmak, düzeltmek, test etmek ve Unity Editor'de görmek— yerine getiremez.

Unity Architect AI bu boşluğu kapatır:

| Geleneksel AI Asistanlar | Unity Architect AI |
|---|---|
| Kod yazar, context görmez | Projenizin tüm `.cs` dosyalarını okur ve indeksler |
| Dosyaya erişemez | Dosya okuma/yazma/silme (onay kapısıyla) |
| Unity Editor'den habersiz | MCP ile sahneye GameObject ekler, Inspector'ı düzenler |
| Terminal çalıştıramaz | Güvenli terminal katmanıyla komut çalıştırır |
| Her sohbet sıfırdan başlar | Kalıcı hafıza ve RAG ile projeyi hatırlar |
| Sadece tek provider | Claude, GPT-4, Gemini, Codex, Ollama desteği |

---

## Özellikler

### Otonom Agentic Loop
- AI görevi aldığında düşünür, araç çağırır, sonucu değerlendirir ve döngü tamamlanana kadar devam eder
- Maksimum 15 iterasyon ile sonsuz döngü koruması
- Her adım kullanıcıya canlı (SSE) akıtılır: `thinking` → `tool_call` → `tool_result` → `response`
- Kullanıcı herhangi bir anda "Durdur" butonuyla iptal edebilir; bekleyen tüm onay kapıları otomatik reddedilir

### Geniş Sağlayıcı Yelpazesi
- **Cloud API**: Anthropic, OpenAI, Google, Groq, DeepSeek, Moonshot/Kimi (+ tümü için OpenRouter alternatifi)
- **Subscription CLI**: Claude Code, Codex CLI, Antigravity CLI (agy) — kullanıcının kendi Anthropic/OpenAI/Google aboneliğinden çalışır
- **Local**: Ollama (`http://localhost:11434`) — yüklü tüm modeller dinamik olarak keşfedilir
- CLI seçilince ilk mesajda backend MCP config dosyalarını otomatik yazar (`~/.claude.json`, `~/.codex/config.toml`, `~/.gemini/antigravity-cli/mcp_config.json`)

### Semantik RAG Motoru
- Tüm `.cs` dosyaları taranır, 1000 karakterlik parçalara bölünür ve vektör olarak indekslenir
- AI bir dosya üzerinde çalışırken ilgili scriptleri, kalıtım ilişkilerini ve bağımlılıkları otomatik çeker
- `/compact` komutuyla uzun sohbetler özetlenir, bağlam kaybı önlenir

### Gerçek Zamanlı C# Linter
- Mono `csc` derleyicisi entegre, kod yazarken arka planda derlenir
- Hatalar Monaco editöründe kırmızı dalgalı çizgi olarak gösterilir
- `Assets/` ve `Library/PackageCache/` (URP, HDRP, vb.) paket referanslarını tanır

### Unity MCP Entegrasyonu
- [CoplayDev/unity-mcp](https://github.com/CoplayDev/unity-mcp) tabanlı, 40+ Unity Editor aracı
- Sahne yönetimi: GameObject oluşturma/silme/düzenleme, bileşen ekleme, Inspector değerleri
- Script yönetimi: Oluşturma, düzenleme, derleme hatalarını alma
- Prefab, material, fizik, animasyon, build ayarları kontrolü
- Çoklu Unity instance desteği: birden fazla açık proje arasında yönlendirme

### Onay Kapısı Sistemi (Approval Gates)
- Tehlikeli her operasyon (dosya yazma, silme, terminal komutu) kullanıcı onayı gerektirir
- Dosya yazma: yan yana diff görüntüsüyle mevcut ve yeni içerik karşılaştırması
- Dosya silme: içerik önizleme ile birlikte silme onayı
- Terminal komutları: komut ve bağlamını gösteren onay kartı
- Onay verilmeden AI tek bir byte değiştiremez

### Hafıza ve Kalıcılık
- Sohbet özetleme: `POST /conversations/{id}/compact` ile bağlam token limitine yaklaşmadan AI tarafından özetlenir ve `conversations.memory_summary` kolonuna yazılır
- Proje hafızası: `app_data/memories/` altında markdown dosyaları olarak saklanır
- RAG indeksi: her analiz sonrası güncellenir
- API anahtarı saklama: Fernet şifreleme + OS keystore (Keychain/Credential Manager) — `api_keys` tablosu sadece şifrelenmiş veri tutar

### Kullanıcı Arayüzü
- **Monaco Editor** — VS Code'un editör motoru, Unity C# sözdizimi desteğiyle
- **Entegre Terminal** — xterm.js tabanlı, sistem komutları ve Unity logları için
- **Diff Görüntüleyici** — Dosya değişikliklerini onaylamadan önce yan yana inceleyin
- **Düşünce Bloğu** — AI'ın düşünme sürecini canlı olarak görün (Claude Extended Thinking, Gemini thinking stream)
- **Model Seçici** — Tüm sağlayıcılar arasında anında geçiş, CLI grupları açılır/kapanır
- **Dosya Gezgini** — Proje hiyerarşisini görsel olarak gezin
- **İki Dilli Arayüz (TR/EN)** — Custom React Context + `useLang()` hook, localStorage ile tercih persist edilir, 100+ çeviri anahtarı

---

## Sistem Mimarisi

```
┌──────────────────────────────────────────────────────┐
│                   Electron Desktop App                │
│  ┌──────────────────────────────────────────────────┐ │
│  │  main/background.ts — LOCAL_APP_TOKEN = uuid()    │ │
│  │  ├─► Backend subprocess env                        │ │
│  │  ├─► MCP subprocess env                            │ │
│  │  └─► Renderer IPC: 'app-token-get'                 │ │
│  └──────────────────────────────────────────────────┘ │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │ Chat Panel  │  │Monaco Editor │  │  Terminal   │ │
│  │ (SSE stream)│  │ (C# linter)  │  │ (xterm.js)  │ │
│  └──────┬──────┘  └──────────────┘  └─────────────┘ │
│         │       React 18 + Next.js 14 (TR/EN i18n)    │
└─────────┼────────────────────────────────────────────┘
          │ HTTP / SSE   +   X-Session-Token header
          ▼
┌──────────────────────────────────────────────────────┐
│                 FastAPI Backend (Python 3.13)          │
│                                                        │
│  ┌─────────────────────────────────────────────────┐  │
│  │              AgentRunner (Agentic Loop)          │  │
│  │   User Request → Think → Tool Call → Result → …  │  │
│  └────────────────────┬────────────────────────────┘  │
│                       │                                │
│         ┌─────────────┼─────────────┐                 │
│         ▼             ▼             ▼                  │
│  ┌────────────┐ ┌──────────┐ ┌──────────────┐         │
│  │ToolRegistry│ │ProjectRAG│ │MemoryManager │         │
│  │read_file   │ │FAISS idx │ │/compact      │         │
│  │write_file  │ │.cs chunks│ │memories/*.md │         │
│  │run_command │ └──────────┘ └──────────────┘         │
│  │search_proj │                                        │
│  └────────────┘                                        │
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │                  AI Providers                     │ │
│  │  Claude API │ OpenAI API │ Gemini API │ Ollama    │ │
│  └──────────────────────────────────────────────────┘ │
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │             MCP Server (FastMCP)                  │ │
│  │  save_file │ read_file │ list_directory │ bash    │ │
│  └──────────────────────────────────────────────────┘ │
└─────────────────────────────────┬────────────────────┘
                                  │ MCP (stdio / HTTP)
          ┌───────────────────────┼───────────────────┐
          ▼                       ▼                    ▼
   ┌─────────────┐       ┌─────────────────┐   ┌──────────────────┐
   │ Claude Code │       │   Codex CLI     │   │ Antigravity CLI  │
   │  (CLI)      │       │   (CLI)         │   │ (agy) — hot-swap │
   └─────────────┘       └─────────────────┘   │ ← gemini-cli-*   │
                                                └──────────────────┘
          │                                            │
          └──────────────────┬─────────────────────────┘
                             │ MCP HTTP (localhost:8080)
                             ▼
                    ┌─────────────────┐
                    │   Unity MCP     │
                    │ (CoplayDev/     │
                    │  unity-mcp)     │
                    │  40+ tools      │
                    └────────┬────────┘
                             │ WebSocket
                             ▼
                    ┌─────────────────┐
                    │  Unity Editor   │
                    │  (C# Plugin)    │
                    └─────────────────┘
```

### Dizin Yapısı

```
unityaıPython/
├── Backend/
│   ├── app/
│   │   ├── agentic/            # AgentRunner, onay kapıları, agent loop
│   │   ├── unity_ai_mcp/       # MCP sunucu (FastMCP) + Unity MCP yöneticisi
│   │   │   ├── tools/          # save_file, delete_file, read_file, list_directory, bash
│   │   │   ├── approval_bridge.py  # Backend ↔ MCP onay köprüsü
│   │   │   └── server.py
│   │   ├── tools/              # Legacy ToolRegistry (direct API agentic için)
│   │   ├── rag/                # ProjectRAG (FAISS), MemoryManager
│   │   ├── knowledge/          # Offline Unity bilgi tabanı
│   │   ├── routes/             # FastAPI router'ları
│   │   │   ├── auth_routes.py            # Lokal token doğrulama (stub /login, /me)
│   │   │   ├── conversation_routes.py    # Chat stream + onay endpoint'leri
│   │   │   ├── config_routes.py          # AI config, model listesi
│   │   │   ├── analysis_routes.py        # Proje analizi, hafıza
│   │   │   ├── lint_routes.py            # C# Roslyn linter
│   │   │   ├── mcp_routes.py             # Unity MCP toggle/status
│   │   │   └── workspace_routes.py       # Workspace yönetimi
│   │   ├── ai_providers.py     # Çoklu sağlayıcı + CLI yönetimi (agy hot-swap dahil)
│   │   ├── auth_utils.py       # LOCAL_APP_TOKEN doğrulama (env var)
│   │   ├── database.py         # SQLite — local user seed (id=1)
│   │   ├── linter.py           # Unity Hub'dan Roslyn yolu çözer
│   │   └── prompts.py          # Sistem promptları, intent sınıflandırıcı
│   ├── tests/                  # pytest test paketi
│   ├── requirements.txt
│   └── Dockerfile
├── Frontend/
│   └── frontend/
│       ├── renderer/
│       │   ├── pages/          # home.tsx (ana IDE), _app.tsx
│       │   ├── components/     # 25+ bileşen
│       │   │   ├── home/       # ChatPanel, DiffViewer, onay UI'ları, editör
│       │   │   └── ui/         # Yeniden kullanılabilir UI bileşenleri
│       │   ├── hooks/          # useChat, useAuth, useAIConfig, useMCPApproval
│       │   └── lib/
│       │       └── i18n.tsx    # TR/EN çeviri context'i, useLang hook
│       └── main/
│           ├── background.ts   # Electron ana süreç, LOCAL_APP_TOKEN üretici
│           └── helpers/        # IPC whitelist, preload
├── unity-mcp/                  # CoplayDev/unity-mcp (submodule)
│   ├── Server/                 # Python MCP sunucusu
│   └── MCPForUnity/            # C# Unity Editor eklentisi
├── LICENSE
└── docker-compose.yml
```

---

## Desteklenen AI Sağlayıcılar

Sağlayıcılar 3 ana kategoriye ayrılır. Bu kategoriler **modelin nereden çalıştığını** belirler — tool kullanımı (MCP / function calling) ayrı bir katmandır ve aşağıdaki *Tool Ekosistemi* bölümünde anlatılır.

### 1. Cloud API (Doğrudan API çağrısı)

Backend ilgili sağlayıcının resmi SDK'sı veya OpenRouter gateway'i üzerinden istek atar. Tool kullanımı **function calling** ile yapılır (model JSON formatında tool çağrısı üretir, backend dispatch eder).

| Sağlayıcı | Örnek Modeller | Notlar |
|---|---|---|
| **Anthropic** | claude-fable-5, claude-opus-4-8, claude-sonnet-4-6, claude-haiku-4-5, claude-opus-4-6 | Extended Thinking, tool use |
| **Google** | gemini-3.1-pro-preview, gemini-3-flash-preview, gemini-3.1-flash-lite-preview, gemini-2.5-pro, gemini-2.5-flash, gemini-2.5-flash-lite | Thinking stream, tool use |
| **OpenAI** | gpt-5.5-pro, gpt-5.5, gpt-5.4, gpt-5.4-mini, gpt-5.4-nano | Function calling, vision |
| **Groq** | llama-3.3-70b-versatile | Düşük gecikme inference (LPU) |
| **DeepSeek** | deepseek-chat (V3) | Uygun fiyatlı genel-amaçlı |
| **Moonshot / Kimi** | kimi-k2.6, kimi-k2.5 | Uzun bağlam (200K+) |
| **OpenRouter** | Yukarıdaki tüm modeller `openrouter_id` ile | Tek API key, tüm sağlayıcılar (yedek yol) |

### 2. Subscription CLI Ajanları

Backend, kullanıcının makinesindeki resmi CLI aracını subprocess olarak çağırır. CLI'nın kendi auth'unu (Anthropic/OpenAI/Google subscription) kullanır. Tool kullanımı **MCP (Model Context Protocol)** ile yapılır — backend her çağrı öncesi CLI'nın okuyacağı `mcp_config.json` dosyasını yazar.

| CLI Aracı | Modeller | Yapılandırma Dosyası |
|---|---|---|
| **Claude Code** | claude-fable-5, claude-opus-4-8, claude-sonnet-4-6, claude-haiku-4-5 | `~/.claude.json` |
| **Codex CLI** | gpt-5.5, gpt-5.4, gpt-5.4-mini | `~/.codex/config.toml` |
| **Antigravity CLI (agy)** | Gemini 3.5 Flash, Gemini 3.1 Pro, Gemini 3 Flash, Gemini 2.5 Pro/Flash + agy üzerinden Claude/GPT-OSS | `~/.gemini/antigravity-cli/mcp_config.json` |

**Şeffaf Hot-Swap (Gemini CLI → agy):** Frontend'de `gemini-cli-*` model ID'leri kalır, backend bunları yakalar (`_AGY_MODEL_MAP`) ve agy binary'sine yönlendirir. agy'nin `--print` modu MCP tool'larını native yüklemediği için (Claude Code/Codex gibi değil), dosya/terminal işlemleri `run_command` ile çağrılan bir `unityai` CLI köprüsü üzerinden yapılır — bu köprü MCP tool'larıyla aynı onay kapısını kullanır, yani agy de onay kartı gösterir (bkz. *Geliştirici Notları — agy Macerası, Sahne 7*).

### 3. Local (Ollama)

Ollama API'si (`http://localhost:11434`) backend tarafından yoklanır; yüklü tüm modeller dinamik olarak listelenir. Sıfır API maliyeti, tam offline çalışma. Function calling destekleyen modeller (örn. Llama 3.3, Qwen2.5) tool kullanabilir.

---

## Tool Ekosistemi (MCP + Function Calling)

Tool kullanımı sağlayıcıdan **bağımsız** bir katmandır. Bir model dosya okumak, yazmak veya terminal komutu çalıştırmak istediğinde iki farklı mekanizma vardır:

| Mekanizma | Hangi Sağlayıcılar | Nasıl Çalışır |
|---|---|---|
| **Function Calling** | Cloud API + Ollama (uyumlu modeller) | Model JSON formatında tool çağrısı üretir, backend'in `AgentRunner`'ı yakalar, `ToolRegistry`'den dispatch eder |
| **MCP (Model Context Protocol)** | Subscription CLI ajanları | CLI bir MCP client'tır, backend'in yazdığı `mcp_config.json` ile MCP server'larına bağlanır, tool'ları stdio veya HTTP üzerinden çağırır |

### MCP Server'ları (Bizim Yazdığımız)

Backend iki MCP server çalıştırır:

1. **Antigravity MCP** (`Backend/app/unity_ai_mcp/server.py`) — `save_file`, `delete_file`, `read_file`, `list_directory`, `bash`. Approval bridge ile dosya yazma/komut çalıştırma onay paneline yönlendirilir
2. **Unity MCP** (CoplayDev/unity-mcp, submodule) — Unity Editor için 40+ tool (sahne, GameObject, prefab, vb.)

### MCP Config'leri Ne Zaman Yazılır?

| Olay | Sonuç |
|---|---|
| Cloud API / Ollama modeli seçilir | MCP config yazılmaz (gerekmiyor — function calling kullanılır) |
| CLI modeli seçilir | Hiçbir şey olmaz (config sadece çağrı anında yazılır) |
| **CLI modeli ile mesaj gönderilir** | `_write_mcp_config()` / `_register_agy_mcp()` çağrılır → CLI'nın config dosyasına **Antigravity MCP** server kaydı yazılır |
| **Unity MCP toggle açılır** | `unity_mcp_manager.start_server()` Unity MCP subprocess'ini başlatır. Bir sonraki CLI çağrısında config dosyalarına `unityMCP` entry'si de eklenir |
| Unity MCP toggle kapatılır | Server durdurulur, sonraki CLI config'lerinden `unityMCP` entry'si çıkarılır |

**Anahtar nokta:** Unity MCP'nin **kendisi** toggle ile başlar/durur. CLI seçimi sadece config dosyalarını yazar — yani bir CLI Unity MCP'ye erişebilmesi için (a) Unity MCP toggle'ı açık olmalı, (b) o CLI ile bir mesaj gönderilmiş olmalı.

### Function Calling tarafında MCP Köprüsü (Yol Haritası)

Şu an Cloud API ve Ollama modelleri kendi `ToolRegistry`'sini kullanır; MCP server'larına doğrudan erişimleri yok. Bu kasıtlı bir mimari sınırdır — API modellerinin tool listesini MCP server'larından dinamik olarak almak için bir köprü katmanı gerekir. Yol haritasında.

---

## Güvenlik Mimarisi

Unity Architect AI, bir AI'nın terminal ve dosya sistemine erişimini güvenli kılmak için çok katmanlı bir savunma mimarisi kullanır:

### 1. Dosya Sistemi Kilidi
- Tüm dosya işlemleri `workspace_path` ile sınırlıdır
- Mutlak yol saldırılarına karşı `Path.resolve()` + prefix kontrolü
- Workspace dışına çıkma girişimleri `PermissionError` ile reddedilir

### 2. Onay Kapısı Katmanı

```
AI bir dosya değiştirmek ister
           │
           ▼
   Değişiklik var mı?
    (strip() karşılaştırma)
      │           │
     Evet        Hayır → "Değişiklik yok" döner
      │
      ▼
  Onay kapısı açılır
  UI'da DiffViewer gösterilir
      │
  ┌───┴───┐
  │       │
Onayla  Reddet
  │       │
Yazar   "Reddedildi" döner
```

### 3. Terminal Güvenliği
- Tehlikeli komutlar kara listeye alınır: `rm -rf`, `sudo`, `curl | bash`, vb.
- Kara listede olmayan komutlar da onay kartı gösterir
- `python3 -c "open().write()"` ve `printf > path` gibi terminal üzerinden dosya yazma girişimleri yakalanır ve DiffViewer'a yönlendirilir
- CLI araçlar için TOML politikası: `run_shell_command`, `replace` gibi built-in araçlar engellenir

### 4. Lokal Token Mimarisi (Ephemeral Session)

Uygulama bir desktop yazılımı olduğu için OAuth/JWT/session DB katmanlarını **kaldırdım**. Yerine **uygulama-yaşam-süresi token'ı** (LOCAL_APP_TOKEN) geldi:

```
Electron başlar → randomUUID() ile token üretir
         │
         ├─► Backend subprocess'ine env var olarak geçirilir
         ├─► MCP server subprocess'ine env var olarak geçirilir
         └─► Renderer'a IPC handler ile sunulur (`app-token-get`)

Her HTTP isteği X-Session-Token header'ı ile gelir
         │
         ▼
Backend `auth_utils._check_token()` env var'la karşılaştırır
         │
     Eşleşmezse → 401
     Eşleşirse  → user_id=1 (tek lokal kullanıcı)
```

- **Tek kullanıcı modeli**: `users` tablosunda yalnızca `id=1, username=local` seed kaydı vardır
- **Token kapsamı**: Sadece o uygulama oturumu için geçerlidir; uygulama kapanınca silinir
- **API anahtarı şifrelemesi**: Fernet + OS keystore (Keychain/Credential Manager) — bu katman korundu

### 5. Web Güvenliği Mirası (Niye Kaldırıldı)

Eski mimaride bcrypt, JWT, OAuth2, rate limiting, oturum DB'si vardı. Hepsi silindi çünkü:
- Bu bir desktop uygulaması, internet üzerinden erişilmiyor
- Kullanıcı zaten cihazına fiziksel erişimi olan kişi
- Multi-user katmanı **sahte güvenlik** veriyordu — saldırgan zaten dosya sistemine erişebilir
- 7 endpoint + 4 DB tablosu + 3 OAuth provider katmanı sadece teknik borç üretiyordu

Sonuç: ~2000 satır auth kodu silindi, sistem daha basit ve daha güvenli oldu.

### 6. MCP Güvenliği (CLI Sağlayıcılar)

```toml
# Otomatik oluşturulan TOML politikası (Gemini CLI)
[[rule]]
toolName = "run_shell_command"
decision = "deny"

[[rule]]
toolName = "replace"
decision = "deny"
```

---

## Kurulum

### Gereksinimler

- Python 3.13+
- Node.js 20+
- Mono (C# linter için, isteğe bağlı)
- Unity Editor (Unity MCP için, isteğe bağlı)

### Backend Kurulumu

```bash
cd Backend

# Sanal ortam oluşturun
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Bağımlılıkları yükleyin
pip install -r requirements.txt

# Ortam değişkenlerini ayarlayın
cp ../.env.example .env
# .env dosyasını düzenleyin (Google/GitHub OAuth anahtarları, vb.)

# Sunucuyu başlatın
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Frontend Kurulumu

```bash
cd Frontend/frontend

# Bağımlılıkları yükleyin
npm install

# Geliştirme modunda başlatın
npm run dev

# Üretim sürümü oluşturun
npm run build
```

### Docker ile Kurulum

```bash
# Tüm servisleri başlatın
docker-compose up -d

# Sadece backend
docker build -t unity-architect-backend ./Backend
docker run -p 8000:8000 unity-architect-backend
```

### Ortam Değişkenleri

```env
# Veritabanı
DB_PATH=~/.unity_architect_ai/unity_master_v3.db

# Sunucu (Electron rastgele boş port seçer; sabit istiyorsan ayarla)
HOST=127.0.0.1
PORT=8000

# API anahtarı şifrelemesi (boş bırakılırsa OS keystore kullanılır)
API_KEY_ENCRYPTION_KEY=
```

> **Not — LOCAL_APP_TOKEN**: Backend, `LOCAL_APP_TOKEN` env var'ını her istekte `X-Session-Token` header'ı ile karşılaştırır. Bu değer **Electron tarafından her uygulama açılışında `randomUUID()` ile üretilir** ve subprocess'lere otomatik olarak geçirilir — manuel ayarlamanıza gerek yoktur. Backend'i standalone (Electron olmadan) çalıştırırsanız bu env var'ı set edebilir veya boş bırakabilirsiniz (boşken token kontrolü atlanır, dev mode).

---

## Kullanım

### 1. Workspace Seçimi
Uygulamayı başlattıktan sonra Unity projenizin klasörünü workspace olarak seçin. Backend bu klasörü tarar ve `.cs` dosyalarını indeksler.

### 2. AI Yapılandırması
Ayarlar menüsünden tercih ettiğiniz sağlayıcıyı ve modeli seçin. API anahtarınızı girin — şifrelenmiş olarak saklanır.

### 3. Sohbet ve Komutlar

```
# Dosya analizi
"PlayerController.cs dosyasındaki performans sorunlarını bul"

# Kod oluşturma
"Inventory sistemi için ScriptableObject tabanlı bir ItemData scripti oluştur"

# Hata düzeltme
"NullReferenceException hatası geliyor, sebebi ne?"

# Unity Editor kontrolü (MCP bağlıysa)
"Sahneye bir Player capsule ekle ve Rigidbody bileşenini bağla"

# Bağlam sıkıştırma
/compact
```

### 4. Onay İş Akışı
AI bir dosya oluşturmak veya değiştirmek istediğinde:
1. Sohbet akışı durur
2. Diff görüntüleyici açılır (mevcut vs. yeni içerik)
3. "Onayla" veya "Reddet" butonuna tıklayın
4. AI onay sonucuna göre devam eder veya alternatif üretir

---

## Unity MCP Entegrasyonu

Unity Architect AI, [CoplayDev/unity-mcp](https://github.com/CoplayDev/unity-mcp) (9.5k yıldız) projesini birleştirir. Bu entegrasyon AI'a Unity Editor'ü doğrudan kontrol etme yeteneği verir.

### Kurulum

**Tamamen Otomatik** — manuel kurulum gerekmez.

1. Unity projenizi açın (Unity Editor açık olmalı)
2. Uygulamada sağ üstteki **Unity MCP toggle**'ına tıklayın
3. Toggle, `unity_mcp_manager` üzerinden Unity MCP sunucusunu başlatır, gerekli bağımlılıkları kurar ve Unity Editor ile bağlantıyı otomatik olarak kurar
4. Toggle yeşile döndüğünde (`Unity bağlandı ✓`) her şey hazırdır

> **Not:** Unity Editor açık değilse toggle bağlanamaz. Önce Unity'yi başlatın, ardından toggle'a basın.

### Mevcut Araçlar (40+)

| Kategori | Araçlar |
|---|---|
| Sahne | `manage_scene`, `find_gameobjects`, `manage_gameobject` |
| Bileşenler | `manage_components`, `manage_physics`, `manage_animation` |
| UI | `manage_ui`, `manage_camera` |
| Prefab | `manage_prefabs`, `manage_scriptable_object` |
| Görseller | `manage_material`, `manage_shader`, `manage_texture`, `manage_graphics` |
| Scripting | `manage_script`, `validate_script`, `apply_text_edits` |
| Build | `manage_build`, `manage_packages`, `manage_editor` |
| VFX | `manage_vfx` |

### Çoklu Instance Desteği

Birden fazla Unity projesi aynı anda açıksa:

```python
# Hangi instance'a komut gitsin
set_active_instance(instance_id="MyGame_2023")
```

---

## Agentic Sistem Detayları

### Araç Çantası (ToolRegistry)

```python
# Mevcut araçlar
read_file(file_path: str)              # Dosya oku (max 500 satır, özet)
write_file(file_path: str, content)    # Dosya yaz (onay gerektirir)
delete_file(file_path: str)            # Dosya sil (onay gerektirir)
list_directory(dir_path: str)          # Klasör içeriğini listele
search_in_project(query: str, exts)    # Semantik proje araması
find_files(pattern: str)               # Dosya adı örüntüsü eşleştirme
run_command(command: str)              # Terminal komutu (güvenlik kontrollü)
save_to_memory(content: str)           # Hafızaya kaydet
recall_memory()                        # Hafızadan oku
```

### SSE Olay Akışı

```
POST /chat → SSE stream açılır

event: thinking
data: {"thinking_text": "Kullanıcı PlayerController sorununu soruyor..."}

event: tool_call
data: {"tool_name": "read_file", "arguments": {"file_path": "Assets/Scripts/Player.cs"}}

event: tool_result
data: {"output": "using UnityEngine;\npublic class PlayerController..."}

event: tool_call
data: {"tool_name": "search_in_project", "arguments": {"query": "GetComponent"}}

event: response
data: {"text": "Update() içinde GetComponent çağrısı buldum. Bunu Start()'a taşıyalım..."}

event: done
data: {}
```

### Intent Sınıflandırıcı

Sistem, her mesajı işlemeden önce amacını sınıflandırır:

- `GENERATION` — Yeni dosya veya kod üretme → Kod pipeline'ı
- `ANALYSIS` — Linting, performans incelemesi → Analiz pipeline'ı
- `CHAT` — Sohbet, soru, planlama → Direkt yanıt (araç çağrısı yok)

Bu sayede "Bir inventory sistemi yapacağız" gibi planlama mesajları gereksiz yere dosya oluşturmaz.

---

## API Referansı

### Temel Endpoint'ler

```
POST /chat
  Body: { user_id, conversation_id, message, model, workspace_path }
  Response: SSE stream

POST /analyze
  Body: { user_id, workspace_path }
  Response: { analysis_report, lint_errors, rag_status }

POST /conversations
  Body: { user_id, title }
  Response: { conversation_id }

POST /compact
  Body: { user_id, conversation_id }
  Response: { summary, tokens_saved }

POST /mcp-abort-all
  Response: { status, rejected_count }
  # Tüm bekleyen onay kapılarını reddeder (stream iptalinde çağrılır)

GET /mcp-approval-result/{gate_id}
  Response: { approved: bool }
  # Frontend'in onay sonucunu yoklaması için

POST /mcp-approval-result/{gate_id}
  Body: { approved: bool }
  # Kullanıcının onay/red kararı
```

### Yapılandırma Endpoint'leri

```
POST /save-ai-config
  Body: { user_id, provider, model, use_multi_agent }

POST /api-keys/save
  Body: { user_id, provider, api_key }  # Şifrelenmiş olarak saklanır

GET /available-models
  Response: { cloud_models, local_models, cli_providers }
```

---

## Geliştirici Notları: Alınan Dersler ve Mimari Kararlar

Bu bölüm projenin evrimindeki gerçek kararları, çıkmaz sokakları ve öğrenilen dersleri belgeler. Commit geçmişi "ne yaptığını" söyler; bu bölüm "neden" sorusunu yanıtlar.

---

### Başlangıç: "Analiz Aracı" Dönemi

Projeyi aslında bir Unity kod **analiz** aracı olarak başlattım. İlk versiyonda kullanıcı bir C# scripti yapıştırıyordu, sistem bunu regex tabanlı statik analizden geçiriyor ve tek bir büyük JSON raporu dönüyordu.

Puanlama sistemi şöyleydi:
```
Final Skor = (Teknik Kalite × 0.60) + (Game Feel × 0.40)
```

8 ayrı ajan vardı: Intent Classifier, Orchestrator, Unity Expert, Critic, Game Feel Agent, Architect, Coder ve Clarification Gate. Her biri kendi token bütçesiyle sırayla çalışıyordu. Kullanıcı "şu scripti düzelt" dediğinde sistem şunu yapıyordu: planla → uzman düzelt → eleştirmen incele → game feel kontrol et → raporla.

**Sorun:** Bu pipeline ortalama 45-60 saniyeydi. Kullanıcı sadece "bu değişkenin adını düzelt" dediğinde bile 8 ajan tetikleniyordu.

**Öğrendiğim ders:** Analitik mimari, interaktif geliştirme için yanlış paradigmadır. Bir rapor aracı ile bir geliştirme ortağı arasındaki fark, kullanıcının bekleme toleransıdır. Rapor için 60 saniye kabul edilebilir; "şunu düzelt" için 60 saniye öldürücüdür.

---

### Partner Mode: "Daha Az Konuşan AI"

Pipeline'ı basite indirdim — 4 adım yerine 2 adım. Daha önemlisi **intent classifier** ekledim.

Klasik bir hatayı çözmek için bunu yapmak zorunda kaldım: Kullanıcı "İnventory sistemi yapacağız, ne düşünüyorsun?" dediğinde sistem bunu GENERATION olarak sınıflandırıyor ve boş bir inventory scripti oluşturmaya başlıyordu. Kullanıcı sadece fikir danışıyordu.

```python
# Eklediğim kural
"kuracağız", "yapacağız", "planla", "düşünüyorum" → CHAT (kod üretme)
"yap", "oluştur", "ekle", "düzelt" → GENERATION
```

**Öğrendiğim ders:** Sınıflandırıcı ne kadar akıllı olursa olsun, intent kural tabanlı sinyallerle zenginleştirilmedikçe hata yapar. LLM'leri "emin değilsen CHAT seç" mantığıyla güvenli tarafa yatırmak gerekiyor.

---

### Büyük Geçiş: Analiz Aracından Agentic IDE'ye

Bu projenin en kritik mimari kararıdır ve bunu yapmak en çok zamanımı aldı.

Önceki modelde kullanıcı sorar, tek seferlik yanıt gelir, sohbet biterdi. AI'nın çalışma dosyalarını görmesi, hata loglarını okuması ya da terminale erişmesi mümkün değildi. Her cevap boşlukta yazılırdı.

**Beni bu karara götüren şey:** Bir kullanıcının "hata şu: NullReferenceException at PlayerController.cs:47, düzelt" mesajıydı. AI 47. satırı göremediği için sadece genel tavsiye verebiliyordu. Bir kıdemliye sorsaydım ne yapardı? Dosyayı açardı, 47. satırı okurdu, bağlamı anlardı, düzeltirdi.

Bu fark, tool use mimarisine geçiş kararını verdirdi:

```
Eski model:  Kullanıcı → [tek LLM çağrısı] → Yanıt
Yeni model:  Kullanıcı → [LLM] → araç çağrısı → [sonuç] → [LLM] → ... → Yanıt
```

`AgentRunner` ve `ToolRegistry` bu geçişin ürünü. Geçiş sonrasında kodun %40'ını yeniden yazdım — bu beklenen bir maliyetti ve erken yapmak gerekiyordu.

---

### main.py Sorunları: God Object Karşı Refactor

Bir noktada `main.py` 2000+ satıra ulaştı. Auth, chat mantığı, OAuth, analiz, konfigürasyon — hepsi tek dosyada. Yeni bir özellik eklemek, bu dosyayı anlamakla başlıyordu; merge conflict'ler normalleşmişti.

Sprint 7-8'de tam bir route refactor yaptım:

```
Önce: main.py (2000+ satır, her şey burada)

Sonra:
├── routes/auth_routes.py        # Sadece auth
├── routes/conversation_routes.py # Sadece chat
├── routes/config_routes.py      # Sadece config
├── routes/analysis_routes.py    # Sadece analiz
├── auth_utils.py                # Session/token helper'ları
└── main.py                      # Sadece bootstrap (~30 satır)
```

Bu refactor sonrasında 3 sprint daha hızlı ilerlediğimi fark ettim.

**Öğrendiğim ders:** "Şimdilik buraya yazayım" kararı er ya da geç ödenir. 2000 satırlık bir dosya sadece kod borcu değil, bilişsel yük borcudur.

---

### MCP Kararı: Neden CLI Katmanı?

Sprint 10'da kritik bir mimari tercih yapmak zorunda kaldım: AI araçları doğrudan backend üzerinden mi çalışsın, yoksa CLI araçları (Claude Code, Codex, Gemini) üzerinden mi?

Doğrudan backend yaklaşımının sorunu: her yeni model için tool calling implementasyonunu yeniden yazmak, her modelin farklı function calling formatını handle etmek ve güvenlik sınırlarını sürekli yeniden inşa etmek.

CLI yaklaşımının avantajı: Claude Code, Codex ve Gemini CLI'nin kendi tool ekosistemi, güvenlik katmanı ve MCP desteği zaten var. Bunların üzerine MCP sunucusu olarak konumlanmak, her CLI'nin gücünü otomatik olarak miras almak demektir.

```
Eski yaklaşım:  Frontend → Backend → [kendi tool kodum] → dosya sistemi
Yeni yaklaşım:  Frontend → Backend → CLI (MCP client) → MCP server → dosya sistemi
```

**Ödediğim maliyet:** 3 farklı CLI konfigürasyon formatını öğrenmek (JSON, TOML, JSON), her birinin davranış farklılıklarını yönetmek zorunda kalmak.

---

### Gemini'nin Gizli Araç Çakışması

Gemini CLI entegrasyonu sırasında ilginç bir sorunla karşılaştım. MCP üzerinden `write_file` isimli araç tanımladım. Gemini CLI'ye bağlandığımda araç görünmüyordu — hata mesajı şuydu:

```
Tool 'mcp_antigravity_write_file' not found
```

Saatlerce log analizi yapmak yerine Gemini CLI'ye doğrudan sordum:
> "Hangi MCP araçlarını görüyorsun ve built-in araç listende `write_file` var mı?"

Cevap açıktı: Gemini CLI'nin `write_file` isimli bir built-in aracı vardı ve aynı isimli MCP araçları susturuluyordu. Adı `save_file` olarak değiştirmek sorunu tamamen çözdü.

**Öğrendiğim ders:** CLI araçlarını debug ederken en hızlı yöntem log analizi değil, aracın kendisine doğrudan sormaktır. 5 dakikada çözüme ulaştım.

---

### JSON Policy'nin Sessiz Başarısızlığı

Gemini CLI için güvenlik politikası yazarken JSON formatı kullandım:

```json
{"rules": [{"toolName": "run_shell_command", "decision": "deny"}]}
```

Hata mesajı yoktu. Policy dosyası okundu, işlendi, kabul edildi. Ama Gemini yine de `run_shell_command`'ı çalıştırıyordu. Uzun süre debug yaptım — ta ki dökümantasyonu dikkatli okuyup TOML formatının zorunlu olduğunu görene kadar:

```toml
[[rule]]
toolName = "run_shell_command"
decision = "deny"
```

**Öğrendiğim ders:** "Hata yok" başarı demek değildir. Güvenlik konfigürasyonlarını her zaman aktif olarak test etmek gerekiyor — özellikle sessizce yanlış giden konfigürasyonlar için.

---

### Stop Butonu: Görünüşte Basit, Gerçekte İki Katmanlı

Kullanıcı "Durdur" butonuna tıkladığında ne olmalı? İlk implementasyonumda AbortController ile SSE stream'i kestim. Frontend yanıt almayı durdurdu.

Ama backend CLI süreci hâlâ çalışıyordu. Ve CLI bir dosyaya yazmak için onay bekliyordu — onay gelene kadar polling yapıyordu. AbortController sadece HTTP bağlantısını kesti; backend'deki bekleme mantığını durdurmadı.

Çözümü iki parça halinde yazdım:
1. `/mcp-abort-all` endpoint'i — tüm bekleyen onay kapılarını reddeder
2. `stopMessage()` her durdurma işleminde bu endpoint'i çağırır

```typescript
stopMessage: () => {
  abortControllerRef.current?.abort();              // SSE bağlantısını kes
  fetch(`${API}/mcp-abort-all`, { method: 'POST' }); // Zombie gate'leri temizle
}
```

**Öğrendiğim ders:** İptal semantiği birden fazla katmanı kapsar. "Frontend iptal etti" ile "işlem iptal edildi" aynı şey değildir. Her async sınırın kendi iptal mekanizması olmalıdır.

---

### Auth'u Söktüm: Multi-User Web Mimarisinden Lokal Desktop'a

Projeyi başlarken refleks olarak web uygulaması paternleriyle yazdım: bcrypt, JWT, session DB, OAuth2 (Google + GitHub), rate limiting. Toplamda ~2000 satır auth kodu, 4 ayrı veritabanı tablosu (`users`, `sessions`, `oauth_states`, `oauth_completions`), 7 endpoint.

Bir gün şunu fark ettim: **Bu bir Electron uygulaması.** Kullanıcı zaten cihazına fiziksel erişimi olan kişi. Multi-user katmanı sadece sahte güvenlik veriyordu — saldırgan zaten `app_data/` klasörüne, API anahtarlarına, kullanıcının dosya sistemine erişebilir. JWT, web saldırı vektörlerine karşı koruma sağlar; lokal bir uygulamada hiçbir saldırı vektörü yok.

Refactor'da auth katmanını tamamen söktüm. Yerine **ephemeral token** geldi:

```typescript
// Frontend/frontend/main/background.ts
const localAppToken = randomUUID()  // Her uygulama açılışında yeni
// Backend ve MCP subprocess'lerine env var olarak geçer
spawn(backend, { env: { ...process.env, LOCAL_APP_TOKEN: localAppToken } })
// Renderer IPC ile alır
ipcMain.handle('app-token-get', () => localAppToken)
```

```python
# Backend/app/auth_utils.py
def _check_token(token):
    expected = os.environ.get("LOCAL_APP_TOKEN", "")
    if expected and token != expected:
        raise HTTPException(401, "Geçersiz token")
    # Boş expected → dev mode, token kontrolü atlanır
```

`users` tablosunda artık tek bir satır var: `(id=1, username='local')`. Sessions/OAuth tabloları DROP edildi.

**Sayısal sonuç:** ~2000 satır kod silindi, 7 endpoint stub'a indirildi (frontend uyumluluğu için), 4 tablo kaldırıldı. Pytest süresi %40 düştü (auth fixture'ları kalktı).

**Öğrendiğim ders:** Mimarinin uygulama bağlamına uygun olması gerekir. Web paternlerini lokal bir uygulamaya kopyalamak, sadece teknik borç üretir. "Bu kod neden burada?" sorusuna verilebilecek tek cevap "çünkü öyle olur" ise, o kod çıkmalı.

---

### agy Macerası: CLI Embed Etmenin Sınırlarını Öğrendim (xD)

Bu, projenin en büyük çıkmaz sokağıydı. Uzun süre bir **uyarı banner'ıyla** idare etti — ta ki doğru kanalı (`run_command` köprüsü) keşfedip **gerçekten çözene** kadar. Hikaye şöyle gelişti.

#### Sahne 1: "27 günümüz var"

Bir sabah Google'ın Gemini CLI'yi 27 gün içinde kapatacağını öğrendim. Yerine Antigravity CLI (`agy`) geliyordu — bir hot-swap geçişi yapmak gerekiyordu. Mantık basit görünüyordu: `--print` modunu çağır, prompt'u stdin'den ver, çıktıyı oku. Claude Code ile aynı pattern.

3 saatlik bir iş gibi durdu. **Üç gün sürdü.**

#### Sahne 2: "Tool çağrıları nerede?"

Hot-swap'i kurdum. agy text yanıtlarını veriyordu. Ama dosya yazma isteklerinde MCP tool'ları **hiç çağrılmıyordu**. Frontend'deki onay paneli açılmıyordu, backend log'larında `CallToolRequest` yoktu.

Saatlerce config dosyalarını döndüm: `mcp_config.json`, `settings.json`, `disabledTools`, `trust: true`. Her şey doğru görünüyordu. agy log'unda **kritik bir satır** vardı:

```
[ERROR] checkpoint model generated tool calls
```

agy'nin kendisine sordum (`agy` çalıştırıp tartıştım — gerçekten). Sonra Codex'e sordum. İkisinin de yorumu aynıydı: **`--print` modu tool dispatch'i tasarım gereği engelliyor.** Model bir tool call üretiyor, agy bunu yakalıyor, "interaktif değilsin, tool çağıramazsın" diyerek LLM'e text-only yanıt için yeniden istek atıyor.

> *İşte burada her şeyin bir ders olduğunu unutup "kesin bir flag bulurum" tuzağına düştüm.*

#### Sahne 3: "`-i` modu kullanırız!"

Çözüm bulduğumu sandım. `--print` yerine `--prompt-interactive` (`-i`) modunu kullanırsam tool'lar çalışırdı. agy ve Codex bunu önerdi:

> "stdin EOF ile graceful exit yap, bubbletea PIPE'ta auto-fallback yapar, bir sorun olmaz."

İlk deneme: `-i` flag'i, stdin PIPE. Sonuç:

```
bubbletea: error opening TTY: bubbletea: could not open TTY:
open /dev/tty: device not configured
```

bubbletea (agy'nin TUI kütüphanesi) PIPE üzerinden çalışmayı reddediyordu. **Gerçek bir PTY gerekiyordu.**

#### Sahne 4: PTY ve Terminal Hijack Felaketi

Python'da `pty.openpty()`, `termios.tcsetattr()` ile echo kapat, `TIOCSWINSZ` ile boyut ayarla, `start_new_session=True` ile parent'tan ayır. Hepsi kitabına göre. Çalıştırdım.

Kullanıcının `npm run dev` çalıştırdığı terminal **agy'nin TUI'sini gösterdi**. Sign-in flow, spinner'lar, "press ctrl+d again to exit", "Bash(git status) için izin ister misin?" promptları — hepsi backend'in spawn ettiği subprocess'ten kullanıcının terminaline akıyordu. Backend ise stdout'tan hiçbir şey okuyamıyordu. 

Bu nasıl mümkündü? `start_new_session=True` ile session ayırmıştım. Ama agy `/dev/tty`'yi parent chain üzerinden buluyor ve oraya yazıyordu. PTY slave'i controlling tty olarak ayarlamak için `TIOCSCTTY` ioctl çağırması gerekiyordu. **Ve daha kötüsü:** `--dangerously-skip-permissions` flag'i `-i` modunda native shell command prompt'larını bypass etmiyordu. Yani PTY çalışsa bile agy hâlâ "git status için izin ver misin?" diye soruyor olacaktı.

#### Sahne 5: Araştırma — Yalnız Değiliz

Web'i taradım. GitHub'da `google-antigravity/antigravity-cli` reposuna baktım. Issue #187 vardı, açık ve Google'dan **yanıt yok**:

> *"Windows: agy.exe produces no stdout when spawned non-interactively (stdio: ['ignore', 'pipe', 'pipe'])"*

Tam bizim sorunumuz, başka bir kullanıcının ağzından. Sonra Gemini API dokümantasyonunda "Antigravity Agent" endpoint'ini buldum:

> *"function_calling and mcp are not yet supported."*

Üstüne agy Google'ın cloud sandbox'ında çalışıyordu — bizim Unity workspace'ine zaten yazamazdı.

Sonuç netti: **`--print` modu MCP tool'larını çalıştırmıyor. `-i` modu interactive TUI gerektiriyor ve otomasyona uygun değil. Antigravity API ise henüz function calling desteklemiyor.** Üç yol da kapalı.

#### Sahne 6: Kabul ve Banner

PTY değişikliklerini geri aldım. `--print` mode'a geri döndüm. agy text yanıt veriyordu — `save_file` MCP tool'umu çağıramıyordu ama en azından kullanıcının terminalini ele geçirmiyordu.

Sonra şunu fark ettim: agy bazı durumlarda dosya yazıyor ve terminal komutu çalıştırıyordu — bizim approval bridge'imizi bypass ederek, Antigravity'nin kendi sandbox'ı üzerinden. Yani kullanıcı için davranış "AI bir şeyler yapıyor ama bana sormuyor" şeklinde gözüküyordu.

Tek dürüst çözüm: **kullanıcıya bunu söylemek.**

```tsx
{isAgyModel && !agyBannerDismissed && (
  <div className="bg-yellow-500/15 border-yellow-500/40 ...">
    <AlertTriangle />
    <span>{t('chat.agyNotice')}</span>
    {/* "Antigravity CLI: dosya yazma ve terminal komutları onay alınmadan
         otomatik çalışır (Google MCP onay entegrasyonu henüz hazır değil)." */}
    <button onClick={dismissAgyBanner}><X /></button>
  </div>
)}
```

Sarı, dismissable, sessionStorage ile persistent. Kullanıcı uygulama açılışında bir kere görüyor, kapatıyor, devam ediyor.

#### Sahne 7: Çözüm — "Yanlış kapıyı çalıyormuşum"

Banner birkaç gün idare etti. Sonra şu soruyu tekrar sordum: *agy unityMCP'yi nasıl kullanıyor?* Çünkü unityMCP **çalışıyordu** — agy sahneye GameObject ekleyebiliyordu. Eğer `--print` MCP'yi hiç yüklemiyorsa, unityMCP nasıl çalışıyordu?

İzole bir testle (sadece unityMCP kayıtlı, agy'ye "tüm araçlarını listele ve `read_console` çağır" dedim) cevabı buldum. agy kendi ağzıyla anlattı:

> *"`read_console` aracım HTTP MCP server üzerinden lazily-loaded; o yüzden workspace'e bir Python script yazıp `streamable_http_client` ile `http://127.0.0.1:8080/mcp`'ye bağlanıp aracı oradan çağırdım."*

**İşte aydınlanma anı buydu.** agy `--print` MCP'yi gerçekten native yüklemiyor (eski teşhisim doğruymuş). Ama agy yeterince akıllı: bir HTTP MCP server'ın URL'ini config'de görünce, `run_command` ile **kendi köprü script'ini yazıp** ona bağlanıyor. unityMCP "çalışıyordu" çünkü HTTP'ydi ve agy ona `run_command` üzerinden ulaşıyordu — MCP protokolüyle değil.

Yani `--print` modunda agy'nin gördüğü **tek gerçek kanal `run_command`.** Bunca zaman yanlış kapıyı çalıyormuşum: MCP tool dispatch'ini zorlamak yerine, `run_command`'ı kullanmalıydım.

**Çözüm — `unityai` CLI köprüsü:**

1. `Backend/app/unityai_cli.py` + `Backend/unityai` (shell wrapper) yazdım. Bu CLI, MCP tool'larıyla **aynı `approval_bridge`'i paylaşıyor** — yani `unityai save-file ...` çağrısı da tıpkı `mcp__unityai__save_file` gibi onay kartını açıyor. agy bunu `run_command` ile çağırıyor.

2. agy'nin **gerçek** built-in yazma araçlarını `disabledTools` ile kapattım: `write_to_file`, `replace_file_content`, `multi_replace_file_content`. (Eski listede `write_file`/`modify_file` gibi **yanlış isimler** vardı — agy'de öyle araçlar yok, o yüzden hiç tutmuyordu. Doğru isimleri agy'nin kendi araç listesini bastırarak öğrendim.) Yazma araçları kapanınca agy dosya oluşturmak için tek yol olarak `run_command`'a düşüyor, biz de onu `unityai save-file`'a yönlendiriyoruz → **onay kartı çıkıyor.**

3. Sarı banner'ı **kaldırdım** — artık yalan söylüyordu. agy de Claude Code/Codex gibi onay kapısından geçiyor.

İzole test + canlı test: agy `unityai save-file`'ı `run_command` ile çağırdı, dosya doğru içerikle ve **onay kartıyla** oluştu. Üç gün boğuştuğum tool dispatch sorunu, doğru soyutlama katmanına (`run_command`) inince çözüldü — tüm hot-swap macerası bir haftaya sığdı.

**Hâlâ duran ufak sıkıntı (dürüstlük payı):** `run_command`'ı kapatamıyoruz — çünkü `unityai` CLI'ını da onunla çağırıyoruz (çıkmaz). Bu yüzden agy teorik olarak ham shell (`echo > x.cs`) ile ya da unityMCP'nin `manage_script` aracına `run_command` köprüsü kurarak onayı **bypass edebilir**. Bunu sadece prompt'la caydırıyoruz; %100 garanti değil. Pratikte yazma araçları kapalı olduğu için agy doğal olarak `unityai`'ye yöneliyor. Karşılaştırma: Claude Code & Codex MCP'yi **native** yüklediği için onlarda `mcp__unityMCP__manage_script` `--disallowedTools` ile **kesin** yasaklı; agy'de bu garanti yok. Kabul edilebilir bir ödünleşme — agy unityMCP'yi sahne kontrolü için serbestçe kullanmaya devam etsin diye.

#### Çıkarılan Dersler

1. **CLI araçlarını embed etmek API entegrasyonundan kategori olarak farklıdır.** Bir CLI, kullanıcı aracı olarak tasarlanır — interaktif TUI, izin promptları, terminal kontrolü. Bunu programatik olarak yönetmek, yanlış katmanı zorlamak demektir.

2. **AI ajanına danışırken doğrulamayı unutma.** agy "PIPE'ta fallback yapar, stdin EOF graceful exit verir" dedi. İkisi de yanlıştı. Codex de aynı şeyi söyledi. AI ajanları, kendi kütüphanelerinin davranışını **hatırlamıyor**, **tahmin ediyor**. Her tavsiyeyi izole bir testle doğrulamak şart.

3. **"Çalışmıyor" bir cevaptır.** Üç gün PTY ile boğuştum çünkü çözmek mümkün olmalıydı. Aslında çözüm yoktu (henüz). Bunu kabul edip kullanıcıya net bilgi vermek, kırılgan bir hack'ten her zaman daha iyidir.

4. **GitHub Issues'i erken kontrol et.** Issue #187 zaten oradaydı. İlk gün baksaydım 2 gün kazanmıştım.

5. **Çıkmaz sokakları belgele.** Bu bölüm bunun için var. Bir sonraki geliştirici (veya 6 ay sonraki ben) aynı yolu yürümesin.

---

### Pratik Kurallar: Projeye Katkı Yaparken Bunları Bilmenizi İstersem

1. **CLI konfigürasyonlarını her zaman global scope'ta yazın.** Gemini CLI headless modda proje seviyesi `.gemini/settings.json`'ı okumaz, sadece `~/.gemini/settings.json`'ı okur.

2. **Approval gate eklerken `strip()` karşılaştırmasını kullanın.** `original == content` trailing newline farkını yakalamaz; diff ekranı gereksiz yere açılır.

3. **MCP araç isimlerini CLI built-in listesiyle karşılaştırın.** Her CLI'nin kendi built-in araçları vardır; isim çakışması sessiz olur.

4. **Intent classifier'ı "güvenli tarafa" yatırın.** Sınır durumlarında GENERATION yerine CHAT seçin. Yanlış dosya oluşturmak, yanlış sohbet etmekten çok daha kötüdür.

5. **Route'ları şimdiden ayırın.** 500 satırı geçen her route dosyası bölünmeli. Bu projedeki en pahalı teknik borç buydu.

6. **Bir CLI'yi subprocess olarak çağırmadan önce upstream Issues'ları tara.** `agy`'yi MCP ile entegre etmek için 3 gün harcadıktan sonra `google-antigravity/antigravity-cli` reposunda Issue #187'yi buldum — tam benim sorunum, Google'dan yanıt yok. 5 dakikalık bir arama 2 günümü kurtarırdı.

7. **AI ajanlarının kendi kütüphaneleri hakkındaki iddialarını doğrula.** agy'ye "PIPE'ta nasıl çalışırsın" diye sordum, "fallback yaparım" dedi. Yalandı. İzole bir test, bir AI yanıtından her zaman daha güvenilirdir.

---

## Katkıda Bulunma

Bu proje aktif geliştirme aşamasındadır. Katkı yapmak isteyenler için:

1. Repo'yu fork'layın
2. Feature branch oluşturun (`git checkout -b feat/amazing-feature`)
3. Backend için `pytest` testlerini çalıştırın: `cd Backend && pytest`
4. Frontend için `vitest` testlerini çalıştırın: `cd Frontend/frontend && npm test`
5. Pull request açın

---

## Geliştirici

**Burak Emre Erdemci**

Bu proje, Unity geliştirme sürecini AI ile kökten dönüştürmek isteyen geliştiriciler için açık kaynaklı bir portfolyo ve araştırma çalışmasıdır.

[MIT Lisansı](LICENSE)
