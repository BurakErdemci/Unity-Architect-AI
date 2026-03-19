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

</div>

## 📋 İçindekiler

- [Özellikler](#-özellikler)
- [Multi-Agent Mimarisi](#-multi-agent-mimarisi)
- [Pipeline Sistemi](#-pipeline-sistemi)
- [Mimari](#-mimari-genel-bakış)
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

| Sağlayıcı | Tür | Kullanım |
|-----------|-----|----------|
| **Anthropic Claude** | ☁️ Bulut | Multi-Agent Pipeline (Tier 2) |
| **Groq** | ☁️ Bulut | Hızlı tek-ajan analiz (Tier 1) |
| **Google Gemini** | ☁️ Bulut | Alternatif bulut sağlayıcı |
| **Ollama** | 🖥️ Yerel | Yerel model desteği |
| **OpenAI / DeepSeek** | ☁️ Bulut | OpenAI uyumlu API'ler |

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

Sistem, her biri belirli bir uzmanlık alanına sahip **7 bağımsız ajan** kullanır:

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
| 🏗️ **Architect** | Sıfırdan mimari plan oluşturur | Kısa tasarım blueprint'i |
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

### 🆕 Tier 3 — Sıfırdan Kod Üretim Pipeline

```
Kullanıcı İsteği → Architect (Plan) → Coder (Kod) → Game Feel (Sessiz Loop) → Final Kod
```

- Architect kısa bir blueprint çıkarır
- Coder 8192 token limitiyle tam mimari üretir
- Game Feel sessiz ve kullanıcıya görünmez şekilde kodu denetler; düşük skorsa Coder tekrar yazar

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
│  │ Analyzer   │  │ Engine   │  │ (7 Ajan)   │              │
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

## 🚀 Kurulum

### Gereksinimler

- **Python 3.9+**
- **Node.js 18+**
- **npm 9+**

### 1. Repoyu Klonla

```bash
git clone https://github.com/BurakErdemci/Unity-Architect-AI.git
cd Unity-Architect-AI
```

### 2. Backend Kurulumu

```bash
cd Backend

# Sanal ortam oluştur
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Bağımlılıkları yükle
pip install -r requirements.txt

# .env dosyası oluştur
cat > .env << EOF
GROQ_API_KEY=gsk_your_groq_key
ANTHROPIC_API_KEY=sk-ant-your_anthropic_key
GEMINI_API_KEY=your_gemini_key
OPENAI_API_KEY=sk-your_openai_key
OLLAMA_BASE_URL=http://127.0.0.1:11434
EOF

# Backend'i başlat
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend Kurulumu

```bash
cd Frontend/frontend

# Bağımlılıkları yükle
npm install

# Uygulamayı başlat (Electron + Next.js)
npm run dev
```

Uygulama otomatik olarak açılacaktır. 🎉

> **Not:** Frontend başlatıldığında Backend çevrimdışıysa otomatik olarak başlatılır.

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

### 🚧 Devam Eden (Sprint 2.2)

- [ ] Built-in Unity Expert (Yerel bilgi bankası + offline destek)
- [ ] Genişletilmiş Statik Analiz kuralları

### 📋 Planlanan

- [ ] Dashboard ve analiz grafikleri
- [ ] Docker desteği
- [ ] PDF rapor dışa aktarma
- [ ] Uygulama paketleme (exe / dmg / AppImage)
- [ ] Geri bildirim öğrenme sistemi (kullanıcı feedback → kural iyileştirme)

---

## 👨‍💻 Geliştirici

**Burak Emre Erdemci**

---

## 📄 Lisans

Bu proje [MIT Lisansı](LICENSE) ile lisanslanmıştır.
