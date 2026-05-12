<div align="center">

# 🏗️ Unity Architect AI

**Unity için Otonom AI Coding Partner**

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Electron](https://img.shields.io/badge/Electron-34-47848F?style=for-the-badge&logo=electron&logoColor=white)](https://electronjs.org)
[![Next.js](https://img.shields.io/badge/Next.js-14-000000?style=for-the-badge&logo=next.js&logoColor=white)](https://nextjs.org)
[![Unity MCP](https://img.shields.io/badge/Unity_MCP-Active-7B2FBE?style=for-the-badge&logo=unity&logoColor=white)](./unity-mcp)

*Sıradan bir chatbot değil — projeyi tanıyan, dosyaları okuyan, kod yazan, terminal çalıştıran ve Unity Editor'ü doğrudan yöneten otonom bir AI geliştirme ortamı.*

[![English](https://img.shields.io/badge/🌐_English_README-blue?style=for-the-badge)](./README_EN.md)
[![Roadmap](https://img.shields.io/badge/🗺️_Yol_Haritası-orange?style=for-the-badge)](./ROADMAP.md)

</div>

---

## Ne Bu?

Unity Architect AI, Unity geliştiricileri için tasarlanmış bir **Agentic IDE**'dir. Claude Code ve Codex CLI benzeri deneyimi Unity dünyasına taşır. Kullanıcıyla sohbet eder, kendi başına dosyaları okur, kod yazar, terminali kullanır ve şimdi Unity Editor'ü MCP üzerinden doğrudan kontrol eder.

---

## Temel Özellikler

### 🧠 AI Partner Modu
Kısa ve direkt. Uzun rapor yok, gereksiz emoji yok. AI, kullanıcının ne dediğini anlayıp en kısa yoldan çözüm üretir. MAX 200 kelime kuralı.

### 🛠️ Agentic Loop
AI'ın gerçek araçları var:
- `read_file`, `write_file`, `list_directory` — projeyi kendi başına gezer
- `run_terminal_command` — git push, npm install, her şey
- Unity MCP araçları — Editor'ü doğrudan yönetir

Her araç kullanımı kullanıcıya gösterilir. Tehlikeli işlemler onay gerektirir.

### 🔌 Unity MCP Entegrasyonu (Phase 5)
AI, Unity Editor'ü doğrudan kontrol eder:

```
Kullanıcı: "Canvas'a bir buton ekle"
       ↓
Router Agent → UI Maestro Expert
       ↓
Unity MCP (localhost:8080)
       ↓
Unity Editor: Button oluşturuldu ✅
```

**Desteklenen işlemler:** GameObject yönetimi, UI Canvas, Script yazma/derleme, Prefab, Material, Sahne yönetimi, Console log okuma.

### 🤖 Subscription Agent Desteği
Kendi bilgisayarındaki **Claude Code** ve **Codex CLI** Antigravity'ye bağlanır. Bu ajanlar dosya ve terminal erişimi için Antigravity'nin **MCP Server'ını** kullanmak zorunda — onay geçmeden hiçbir tehlikeli işlem yapamaz.

### 🛡️ Onay Sistemi
- **Diff Viewer** — kod değişiklikleri önce gösterilir
- **Command Approval** — terminal komutları onaylanır  
- **Ephemeral Snapshot** — değişiklik onaylanana kadar disk'e yazılmaz

### 💡 Akıllı Kod Üretimi
- Kullanıcı dosyayı sürükler veya komut yazar
- Plan / Otomatik / Adım-adım modları
- AI kodu yazar, editörde açar, hataları gösterir

### 🔬 C# Linter (Gerçek Derleyici)
AI tahmini değil, gerçek **Mono `csc`** derleyicisi. Hata satır/sütun bilgisiyle Monaco editörde kırmızı dalgalı çizgi olarak gösterilir. Proje açılınca otomatik tüm `.cs` dosyaları taranır.

### 🧠 Hafıza (Architect Wisdom)
Sohbetin başında AI, projenin önceki analizinden bir özet (Architect Wisdom paneli) gösterir. `/compact` ile geçmiş özetlenerek token alanı açılır.

### 💻 Entegre Terminal
VS Code tarzı terminal paneli. Problems / Output / Terminal sekmeleri. Hata listesinde tıkla, ilgili satıra git.

### 🤖 Çoklu AI Sağlayıcı
Claude, GPT, Gemini, Groq, DeepSeek, Ollama, OpenRouter, Moonshot — tek arayüz.

---

## Mimari

```
┌────────────────────────────────────────────┐
│          ELECTRON DESKTOP APP              │
│  Dosya Gezgini | Monaco Editör | AI Chat   │
│  Terminal Paneli | Problems | Diff Viewer  │
└──────────────────┬─────────────────────────┘
                   │ HTTP REST + SSE
┌──────────────────▼─────────────────────────┐
│        PYTHON BACKEND (FastAPI)            │
│                                            │
│  Router Agent → AI Provider (Claude/GPT..) │
│  Agentic Loop (Tool Use) → SSE Stream      │
│                                            │
│  Antigravity MCP Server (FastMCP)          │
│  ├── file_tools (read/write/list)          │
│  ├── bash_tool (terminal + onay kapısı)    │
│  └── Subscription CLI Bridge              │
└──────────────────┬─────────────────────────┘
                   │ HTTP / WebSocket
┌──────────────────▼─────────────────────────┐
│       UNITY EDITOR (unity-mcp)             │
│  GameObject | Script | UI | Scene | Build  │
└────────────────────────────────────────────┘
```

---

## İndir

| Platform | Link |
|----------|------|
| 🍎 macOS (Apple Silicon) | [arm64.dmg](https://github.com/BurakErdemci/Unity-Architect-AI/releases/download/v1.0.0/Unity.Architect.AI-1.0.0-arm64.dmg) |
| 🍎 macOS (Universal) | [universal.dmg](https://github.com/BurakErdemci/Unity-Architect-AI/releases/download/v1.0.0/Unity.Architect.AI-1.0.0.dmg) |
| 🪟 Windows | [Setup.exe](https://github.com/BurakErdemci/Unity-Architect-AI/releases/download/v1.0.0/Unity.Architect.AI.Setup.1.0.0.exe) |

> macOS "Hasar görmüş" hatası: `xattr -cr /Applications/Unity\ Architect\ AI.app`

---

## Kurulum (Geliştirici)

**Gereksinim:** Python 3.13, Node.js 18+

```bash
# 1. Repo
git clone https://github.com/BurakErdemci/Unity-Architect-AI.git
cd Unity-Architect-AI

# 2. Backend
cd Backend
python3.13 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Frontend
cd ../Frontend/frontend
npm install
npm run dev
```

> **Docker:** `docker compose up --build -d` → `npm run dev:docker`

---

## Teknoloji

| Katman | Teknoloji |
|--------|-----------|
| **Backend** | Python 3.13, FastAPI, FastMCP, SQLite, Uvicorn |
| **Frontend** | Electron 34, Next.js 14, React 18, Tailwind CSS, Monaco Editor |
| **AI** | Claude, GPT, Gemini, Groq, DeepSeek, Ollama, OpenRouter |
| **Unity Bridge** | unity-mcp, MCPForUnity, WebSocket Hub |
| **Güvenlik** | MCP Onay Kapısı, Ephemeral Snapshot, IPC Whitelist, safeStorage |

---

## Sprint Geçmişi (Kısa)

| Sprint | Ne Yapıldı |
|--------|-----------|
| 1-2 | Partner mod, intent classifier, pipeline sadeleştirme, thinking sistemi |
| 3-4 | Agentic Loop (tool use), Architect Wisdom hafıza paneli, SSE streaming |
| 5-6 | Entegre terminal, C# Linter (Mono csc), Monaco marker entegrasyonu |
| 7-8 | Otomatik proje radarı, otonom terminal, Git komut zinciri |
| 9-11 | Claude Code + Codex MCP entegrasyonu, Onay Kapısı, Ephemeral Snapshot |
| 12+ | Unity MCP entegrasyonu, Expert Agent Swarm (aktif) |

Detaylar → [LOCAL_REFACTOR_NOTES.md](./LOCAL_REFACTOR_NOTES.md) · [ROADMAP.md](./ROADMAP.md)

---

## 👨‍💻 Geliştirici

**Burak Emre Erdemci**

## 📄 Lisans

Bu proje [MIT Lisansı](LICENSE) ile lisanslanmıştır.

### Üçüncü Taraf Lisanslar

Bu proje, Unity Editor entegrasyonu için aşağıdaki açık kaynak bileşeni içerir:

| Bileşen | Kaynak | Lisans |
|---------|--------|--------|
| **unity-mcp** (MCPForUnity) | [CoplayDev/unity-mcp](https://github.com/CoplayDev/unity-mcp) | [MIT](./unity-mcp/LICENSE) — Copyright (c) 2025 CoplayDev |
