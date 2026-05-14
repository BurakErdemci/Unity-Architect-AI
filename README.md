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

[English README](./README_EN.md) · [Yol Haritası](./ROADMAP.md)

</div>

---

## İçindekiler

- [Neden Unity Architect AI?](#-neden-unity-architect-ai)
- [Özellikler](#-özellikler)
- [Sistem Mimarisi](#-sistem-mimarisi)
- [Desteklenen AI Sağlayıcılar](#-desteklenen-ai-sağlayıcılar)
- [Güvenlik Mimarisi](#️-güvenlik-mimarisi)
- [Kurulum](#-kurulum)
- [Kullanım](#-kullanım)
- [Unity MCP Entegrasyonu](#-unity-mcp-entegrasyonu)
- [Agentic Sistem Detayları](#-agentic-sistem-detayları)
- [API Referansı](#-api-referansı)
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

### Çoklu CLI Sağlayıcı Desteği
- **Claude Code** — Anthropic'in resmi CLI aracı, MCP entegrasyonuyla
- **Codex CLI** — OpenAI'ın otonom kodlama CLI aracı
- **Gemini CLI** — Google'ın açık kaynak CLI aracı (OAuth ile Google AI Pro desteği)
- Her CLI için MCP yapılandırması otomatik oluşturulur (`~/.claude.json`, `~/.codex/config.toml`, `~/.gemini/settings.json`)

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
- Sohbet özetleme: `/compact` ile bağlam token limitine yaklaşmadan hafızaya alınır
- Proje hafızası: `app_data/memories/` altında markdown dosyaları olarak saklanır
- RAG indeksi: her analiz sonrası güncellenir

### Kullanıcı Arayüzü
- **Monaco Editor** — VS Code'un editör motoru, Unity C# sözdizimi desteğiyle
- **Entegre Terminal** — xterm.js tabanlı, sistem komutları ve Unity logları için
- **Diff Görüntüleyici** — Dosya değişikliklerini onaylamadan önce yan yana inceleyin
- **Düşünce Bloğu** — AI'ın düşünme sürecini canlı olarak görün (Claude Extended Thinking, Gemini thinking stream)
- **Model Seçici** — Tüm sağlayıcılar arasında anında geçiş, CLI grupları açılır/kapanır
- **Dosya Gezgini** — Proje hiyerarşisini görsel olarak gezin

---

## Sistem Mimarisi

```
┌──────────────────────────────────────────────────────┐
│                   Electron Desktop App                │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │ Chat Panel  │  │Monaco Editor │  │  Terminal   │ │
│  │ (SSE stream)│  │ (C# linter)  │  │ (xterm.js)  │ │
│  └──────┬──────┘  └──────────────┘  └─────────────┘ │
│         │              React 18 + Next.js 14          │
└─────────┼────────────────────────────────────────────┘
          │ HTTP / SSE
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
   ┌─────────────┐       ┌─────────────────┐   ┌────────────┐
   │ Claude Code │       │   Codex CLI     │   │ Gemini CLI │
   │  (CLI)      │       │   (CLI)         │   │  (CLI)     │
   └─────────────┘       └─────────────────┘   └────────────┘
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
│   │   ├── agentic/            # AgentRunner, onay kapıları
│   │   ├── mcp/                # MCP sunucu, araçlar, Unity MCP yöneticisi
│   │   │   └── tools/          # save_file, bash, read_file, list_directory
│   │   ├── tools/              # ToolRegistry (554 satır), araç tanımları
│   │   ├── rag/                # ProjectRAG (FAISS), MemoryManager
│   │   ├── knowledge/          # Offline Unity bilgi tabanı
│   │   ├── routes/             # 7 API router (sohbet, auth, config, analiz, lint, mcp, workspace)
│   │   ├── ai_providers.py     # Çoklu sağlayıcı entegrasyonu + CLI yönetimi
│   │   ├── database.py         # SQLite şifrelemeli veritabanı
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
│       │   └── hooks/          # useChat, kullanıcı durum hook'ları
│       └── main/               # Electron ana süreç, preload
├── unity-mcp/                  # CoplayDev/unity-mcp (submodule)
│   ├── Server/                 # Python MCP sunucusu
│   └── MCPForUnity/            # C# Unity Editor eklentisi
├── ROADMAP.md
└── docker-compose.yml
```

---

## Desteklenen AI Sağlayıcılar

### Doğrudan API (Backend üzerinden)

| Sağlayıcı | Modeller | Özellikler |
|---|---|---|
| **Anthropic Claude** | claude-opus-4-7, claude-sonnet-4-6, claude-haiku-4-5 | Extended Thinking, araç kullanımı |
| **Google Gemini** | gemini-2.5-pro, gemini-2.5-flash, gemini-3.1-pro-preview | Thinking stream, araç kullanımı |
| **OpenAI** | gpt-4o, gpt-4, gpt-3.5-turbo | Fonksiyon çağırma, görüntü |
| **Ollama** | Yerel her model (Llama, Mistral, vb.) | Sıfır API maliyeti, gizlilik |
| **Bilgi Tabanı** | — | Çevrimdışı, anında yanıt |

### CLI Sağlayıcılar (MCP üzerinden otonom çalışma)

| CLI | Yapılandırma | Notlar |
|---|---|---|
| **Claude Code** | `~/.claude.json` | Anthropic'in resmi CLI aracı |
| **Codex CLI** | `~/.codex/config.toml` | OpenAI Codex CLI |
| **Gemini CLI** | `~/.gemini/settings.json` | Google AI Pro aboneliği desteği |

CLI sağlayıcılar seçildiğinde backend otomatik olarak:
1. MCP yapılandırma dosyalarını oluşturur (Antigravity MCP + Unity MCP)
2. Güvenlik politikasını yazar (tehlikeli araçlar engellenir)
3. CLI'yi doğru workspace ve parametrelerle başlatır
4. Yanıtları SSE stream olarak frontend'e iletir

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

### 4. Ağ ve Auth Güvenliği
- Bcrypt ile parola hashleme
- Fernet şifrelemeli API anahtarı saklama (birincil: OS keystore, yedek: şifreli dosya)
- JWT + oturum token'ı (yapılandırılabilir TTL, varsayılan 24 saat)
- OAuth2 (Google, GitHub)
- Rate limiting: kullanıcı başına dakikada 15 istek

### 5. MCP Güvenliği (CLI Sağlayıcılar)

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
# OAuth (isteğe bağlı)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=

# Veritabanı
DB_PATH=~/.unity_architect_ai/unity_master_v3.db

# Sunucu
HOST=127.0.0.1
PORT=8000

# Oturum
SESSION_TTL_MINUTES=1440

# API anahtarı şifrelemesi (boş bırakılırsa otomatik oluşturulur)
API_KEY_ENCRYPTION_KEY=
```

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

**1. Unity Paketini Yükleyin**

Unity projenizin `Packages/manifest.json` dosyasına ekleyin:

```json
{
  "dependencies": {
    "com.coplaydev.unity-mcp": "https://github.com/CoplayDev/unity-mcp.git?path=/MCPForUnity"
  }
}
```

**2. MCP Sunucusunu Başlatın**

```bash
cd unity-mcp/Server
pip install -e .
python -m mcp_for_unity
# Varsayılan port: 8080
```

**3. Unity'de Bağlantıyı Doğrulayın**

Unity Editor'ü açın → `Window > MCP For Unity` → Bağlantı durumunu kontrol edin.

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

### Pratik Kurallar: Projeye Katkı Yaparken Bunları Bilmenizi İstersem

1. **CLI konfigürasyonlarını her zaman global scope'ta yazın.** Gemini CLI headless modda proje seviyesi `.gemini/settings.json`'ı okumaz, sadece `~/.gemini/settings.json`'ı okur.

2. **Approval gate eklerken `strip()` karşılaştırmasını kullanın.** `original == content` trailing newline farkını yakalamaz; diff ekranı gereksiz yere açılır.

3. **MCP araç isimlerini CLI built-in listesiyle karşılaştırın.** Her CLI'nin kendi built-in araçları vardır; isim çakışması sessiz olur.

4. **Intent classifier'ı "güvenli tarafa" yatırın.** Sınır durumlarında GENERATION yerine CHAT seçin. Yanlış dosya oluşturmak, yanlış sohbet etmekten çok daha kötüdür.

5. **Route'ları şimdiden ayırın.** 500 satırı geçen her route dosyası bölünmeli. Bu projedeki en pahalı teknik borç buydu.

---

## Katkıda Bulunma

Bu proje aktif geliştirme aşamasındadır. Katkı yapmak isteyenler için:

1. Repo'yu fork'layın
2. Feature branch oluşturun (`git checkout -b feat/amazing-feature`)
3. Backend için `pytest` testlerini çalıştırın: `cd Backend && pytest`
4. Frontend için `vitest` testlerini çalıştırın: `cd Frontend/frontend && npm test`
5. Pull request açın

---

## Yol Haritası

Projenin detaylı yol haritası için [ROADMAP.md](./ROADMAP.md) dosyasına bakın.

**Aktif Sprint (Phase 5):** Unity MCP tam entegrasyonu + Expert Agent Swarm (8 uzman agent: UI Maestro, Prefab Architect, Scene Director, VFX Artist, Physics Expert, Animation Expert, Script Writer, Build Manager)

---

## Geliştirici

**Burak Emre Erdemci**

Bu proje, Unity geliştirme sürecini AI ile kökten dönüştürmek isteyen geliştiriciler için açık kaynaklı bir portfolyo ve araştırma çalışmasıdır.

[MIT Lisansı](LICENSE)
