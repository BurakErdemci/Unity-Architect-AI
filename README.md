<div align="center">

# 🏗️ Unity Architect AI

**Yapay Zeka Destekli Unity C# Kod Analiz ve Geliştirme Platformu**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Electron](https://img.shields.io/badge/Electron-34-47848F?style=for-the-badge&logo=electron&logoColor=white)](https://electronjs.org)
[![Next.js](https://img.shields.io/badge/Next.js-14-000000?style=for-the-badge&logo=next.js&logoColor=white)](https://nextjs.org)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://reactjs.org)

*Unity geliştiricileri için profesyonel seviyede kod denetimi, performans analizi ve AI destekli kod düzeltme.*

---

<!-- Buraya uygulamanın bir ekran görüntüsü eklenecek -->
<!-- ![Unity Architect AI Screenshot](docs/screenshot.png) -->

</div>

## 📋 İçindekiler

- [Özellikler](#-özellikler)
- [Mimari](#-mimari)
- [Kurulum](#-kurulum)
- [Kullanım](#-kullanım)
- [Teknoloji Yığını](#-teknoloji-yığını)
- [Proje Yapısı](#-proje-yapısı)
- [API Dokümantasyonu](#-api-dokümantasyonu)
- [Yol Haritası](#-yol-haritası)
- [Lisans](#-lisans)

---

## ✨ Özellikler

### 🔍 3 Aşamalı Kademeli Analiz Pipeline

| Aşama | İşlem | Süre |
|-------|-------|------|
| **Step 1** — Statik Analiz | Python tabanlı regex analiz + ağırlıklı puanlama | ~10ms |
| **Step 2** — Derin Analiz | AI ile açıklama, benzetme ve öneriler | ~2-3s |
| **Step 3** — Kod Düzeltme | AI ile düzeltilmiş kodun tam üretimi | ~2-3s |

### 📊 Akıllı Puanlama Sistemi
- **0-10 arası ağırlıklı skor** — Performans hataları daha çok ceza alır
- **Diminishing returns** — Aynı kategoriden tekrar eden hatalar azalan ceza alır
- **Severity sınıflandırma** — 🔴 Kritik, 🟡 Uyarı, 🔵 Bilgi
- **Kategori bazlı skor** — Performans, Fizik, Mantık, Mimari, Best Practice, Stil

### 🖥️ IDE Benzeri Kullanıcı Arayüzü
- **3 panel layout** — Dosya Gezgini | Kod Editörü | AI Chat
- **Cursor IDE tarzı** tasarım — koyu tema, yumuşak animasyonlar
- **Syntax highlighting** — C# kod renklendirme
- **Markdown render** — AI yanıtlarında zengin format
- **Dosya sürükle-bırak** — .cs dosyalarını direkt editöre bırak

### 🏗️ Workspace Sistemi
- **Login → Workspace Seç → Uygulama** akışı
- Son açılan workspace'i hatırlar
- Workspace kapatma ve değiştirme
- Boş klasörlerde bile çalışır

### 🤖 Çoklu AI Sağlayıcı Desteği

| Sağlayıcı | Tür | API Key |
|-----------|-----|---------|
| **Groq** (Varsayılan) | ☁️ Bulut | `.env` dosyasında |
| **Ollama** | 🖥️ Yerel | Gerekmez |
| **Google Gemini** | ☁️ Bulut | Gerekir |
| **OpenAI (GPT)** | ☁️ Bulut | Gerekir |
| **DeepSeek** | ☁️ Bulut | Gerekir |

### 🔎 Tespit Edilen Kod Sorunları

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

## 🏛️ Mimari

```
┌─────────────────────────────────────────────────────────┐
│                    ELECTRON (Nextron)                     │
│  ┌──────────┐  ┌─────────────────┐  ┌────────────────┐  │
│  │ Dosya    │  │   Kod Editörü   │  │   AI Chat      │  │
│  │ Gezgini  │  │   (Monaco-like) │  │   (Markdown)   │  │
│  │          │  │                 │  │                │  │
│  │ .cs      │  │  C# syntax     │  │  Pipeline      │  │
│  │ files    │  │  highlight     │  │  Score Badge   │  │
│  └──────────┘  └─────────────────┘  └───────┬────────┘  │
│                                              │           │
└──────────────────────────────────────────────┼───────────┘
                                               │ HTTP
┌──────────────────────────────────────────────┼───────────┐
│                 PYTHON BACKEND (FastAPI)      │           │
│  ┌─────────────┐  ┌──────────────┐  ┌───────▼────────┐  │
│  │ Statik      │  │ Report       │  │ Pipeline       │  │
│  │ Analyzer    │  │ Engine       │  │ Orchestrator   │  │
│  │ (regex)     │  │ (scoring)    │  │ (3-step)       │  │
│  └──────┬──────┘  └──────┬───────┘  └───────┬────────┘  │
│         │                │                   │           │
│         └────────────────┼───────────────────┘           │
│                          │                               │
│  ┌───────────────┐  ┌────▼────┐  ┌────────────────────┐  │
│  │ AI Providers  │  │ SQLite  │  │ Prompt Engineering │  │
│  │ (5 sağlayıcı) │  │  DB     │  │ (multi-step)      │  │
│  └───────────────┘  └─────────┘  └────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

---

## 🚀 Kurulum

### Gereksinimler

- **Python 3.11+**
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

# .env dosyası oluştur (opsiyonel — Groq için)
echo "GROQ_API_KEY=gsk_your_api_key_here" > .env

# Backend'i başlat
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend Kurulumu

```bash
cd Frontend/frontend

# Bağımlılıkları yükle
npm install

# Uygulamayı başlat
npm run dev
```

Uygulama otomatik olarak açılacaktır. 🎉

---

## 💡 Kullanım

### Temel Akış

1. **Giriş Yap** — Kullanıcı adı ve şifre ile kayıt ol / giriş yap
2. **Workspace Seç** — Unity projenin `Assets/Scripts` klasörünü seç
3. **Dosya Seç** — Sol panelden bir `.cs` dosyasına tıkla
4. **Analiz Et** — Sağdaki chat'e "Bu kodu analiz et" yaz
5. **Sonuçları İncele** — Skor badge, bulgular ve düzeltilmiş kod

### Örnek Kullanım Senaryoları

| Senaryo | Nasıl |
|---------|-------|
| Mevcut kodu analiz et | Dosyayı seç → "Analiz et" |
| Belirli bir sorun sor | "Bu koddaki performans sorunları neler?" |
| Genel Unity sorusu | "Unity'de Object Pooling nasıl yapılır?" |

---

## 🛠️ Teknoloji Yığını

### Backend
| Teknoloji | Kullanım |
|-----------|----------|
| **Python 3.11** | Ana backend dili |
| **FastAPI** | REST API framework |
| **SQLite** | Kullanıcı verileri, sohbet geçmişi, workspace |
| **Uvicorn** | ASGI sunucu |
| **Ollama** | Yerel AI model yönetimi |
| **python-dotenv** | Ortam değişkenleri |
| **passlib + bcrypt** | Şifre hash'leme |

### Frontend
| Teknoloji | Kullanım |
|-----------|----------|
| **Electron 34** | Masaüstü uygulama çerçevesi |
| **Next.js 14** | React framework |
| **React 18** | UI bileşenleri |
| **Tailwind CSS** | Stil sistemi |
| **Framer Motion** | Animasyonlar |
| **react-markdown** | Markdown render |
| **react-syntax-highlighter** | Kod renklendirme |
| **Lucide React** | İkon kütüphanesi |

### Araçlar
| Araç | Kullanım |
|------|----------|
| **Nextron** | Electron + Next.js entegrasyonu |
| **electron-builder** | Uygulama paketleme (exe/dmg) |
| **Axios** | HTTP istemci |

---

## 📁 Proje Yapısı

```
Unity-Architect-AI/
├── Backend/
│   ├── app/
│   │   ├── main.py              # FastAPI uygulama + endpointler
│   │   ├── analyzer.py          # Statik kod analiz motoru (regex)
│   │   ├── pipeline.py          # 3 aşamalı analiz orchestrator
│   │   ├── report_engine.py     # Ağırlıklı puanlama sistemi
│   │   ├── prompts.py           # AI prompt şablonları
│   │   ├── ai_providers.py      # Çoklu AI sağlayıcı yönetimi
│   │   ├── database.py          # SQLite veritabanı yönetimi
│   │   └── validator.py         # Yanıt doğrulama
│   ├── requirements.txt
│   └── .env                     # API anahtarları (git'e eklenmez)
│
├── Frontend/
│   └── frontend/
│       ├── main/
│       │   ├── background.ts    # Electron ana süreç
│       │   └── preload.ts       # IPC köprüsü
│       ├── renderer/
│       │   ├── pages/
│       │   │   └── home.tsx     # Ana uygulama bileşeni
│       │   └── styles/
│       │       └── globals.css  # Genel stiller
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
| `POST` | `/chat` | AI ile sohbet (pipeline aktif) |
| `POST` | `/analyze` | Statik kod analizi |
| `POST` | `/save-ai-config` | AI sağlayıcı ayarlarını kaydet |
| `GET` | `/available-models` | Mevcut AI modellerini listele |
| `POST` | `/conversations` | Yeni sohbet oluştur |
| `GET` | `/conversations/{user_id}` | Kullanıcının sohbetleri |
| `POST` | `/save-workspace` | Workspace yolunu kaydet |
| `GET` | `/last-workspace/{user_id}` | Son workspace yolunu getir |
| `POST` | `/write-file` | Dosya yaz (workspace içinde) |

---

## 🗺️ Yol Haritası

- [x] IDE benzeri 3 panel arayüz
- [x] Çoklu AI sağlayıcı desteği (Groq, Ollama, Gemini, OpenAI, DeepSeek)
- [x] Statik kod analiz motoru (Unity C# regex kuralları)
- [x] Sohbet sistemi (çoklu konuşma, geçmiş)
- [x] 3 aşamalı kademeli analiz pipeline
- [x] Ağırlıklı puanlama sistemi (diminishing returns)
- [x] Workspace yönetim sistemi
- [ ] Geri bildirim öğrenme sistemi (kullanıcı feedback → prompt iyileştirme)
- [ ] Sıfırdan kod üretme modu (GENERATION pipeline)
- [ ] Dashboard ve analiz grafikleri
- [ ] Docker desteği
- [ ] Otomatik test suite (pytest)
- [ ] PDF rapor dışa aktarma
- [ ] Uygulama paketleme (exe / dmg / AppImage)

---

## 👨‍💻 Geliştirici

**Burak Emre Erdemci**

---

## 📄 Lisans

Bu proje [MIT Lisansı](LICENSE) ile lisanslanmıştır.
