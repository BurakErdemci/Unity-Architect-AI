# Değişiklik günlüğü

Bu dosya kullanıcıya görünen değişiklikleri taşır. Tam geçmiş için `git log`.

> ℹ️ **8 Ağu 2026'dan itibaren yeni girdiler İngilizce yazılıyor.** Sebep: bu
> dosyanın en üst bölümü `RELEASE_NOTES.md`'ye taşınıyor ve orası yabancı bir
> kullanıcının indirme anında gördüğü sayfa. Eski girdiler olduğu gibi bırakıldı —
> geçmişi yarım çevirmek, tek dilde bırakmaktan da iki dilde bırakmaktan da kötü.

## Unreleased

### The project is now plain MIT

The Commons Clause condition has been removed; `LICENSE` is now the MIT licence
alone. The project is therefore open source in the OSI sense, and the READMEs say
so instead of "source-available".

Why the change: Commons Clause bought a signal, not enforcement — it does not stop
a determined closed fork, while it costs the OSI label, keeps the repository out of
package directories, deters contributors, and (unintentionally) prohibited paid
third-party support, which was never the intent. Selling a fork of the application
is now permitted. Already-released versions keep the terms they shipped with.

`unity-mcp/` remains MIT (c) 2025 CoplayDev under its own `LICENSE`, and the
third-party notices are unchanged.

## v3.0.3 — 9 Ağustos 2026

### Compact now actually shrinks the context

Compact summarised the chat and left the model's context exactly where it was.
You could press it, watch the conversation collapse into a summary, ask the CLI
how much context it was holding, and get the same number back — 773k of 1M
tokens, unchanged. Measured live, not inferred.

Two things were wrong, and the first one hid the second.

**The session was being revived.** Compact closed the live CLI session, which
used to be enough. Since 3.0.1 the app also remembers each chat's CLI session id
so it can resume where you left off — and nothing dropped that id on compact. The
next message resumed the old session, the CLI reloaded its full transcript from
disk, and the session we had just closed came back exactly as it was. Worse, on a
resumed session the freshly written summary is deliberately *not* injected, so
the old context returned and the new summary never arrived.

**Short chats skipped the reset entirely.** Compact returned early when the chat
had six messages or fewer — reasonable for summarising, wrong for resetting. After
one compact the stored chat *is* short, while the CLI session is still full. So
the second press reported "chat is already short" and reset nothing, which is the
state most people would hit.

Compact now drops the session id in both paths, so a short chat still gets a clean
CLI session. The message you get in that case says what actually happened, and it
now comes from the dictionary — English UI no longer shows a Turkish toast here.

### Windows installer name is fixed at the source

The installer has shipped as `Gamachine.Setup.X.Y.Z.exe` for three releases while
the update feed asked for `Gamachine-Setup-X.Y.Z.exe`, and the gap was closed by
hand every time. The dots come from NSIS's default name template, not from the
product name. The template is now pinned, so the build and the update feed agree
without anyone remembering to intervene.

## v3.0.2 — 9 Ağustos 2026

### The agent can now play a game it is not looking at

`manage_input` — the tool that hands your game to the agent — worked in demos
and failed in real use. The difference was never the input path. While you are
in the chat window Unity sits fully unfocused, and two separate things happen
there. Both were measured live against a running editor, with the window in the
background the whole time.

**The engine stops.** Play mode enters, `timeScale` reads 1, and the game sits
frozen at frame 2. Every key we sent was correct and no frame ever processed it.
The project's own *Run In Background* setting was already on and did not help —
the runtime value is separate and starts off.

**The devices get switched off.** The Input System's default behaviour disables
every device when the application loses focus, the real keyboard and mouse
included. The key arrives at a device nobody is listening to.

Both are now handled on the input path, so pressing Play by hand does not
quietly change how your editor behaves. Nothing is written to your project: the
settings we take over are handed back when play mode exits.

`describe` now reports whether the game is actually running. It used to answer
"can input reach the game" by listing resolved members and said yes while the
engine was frozen — and no focus flag can catch that, because during the freeze
Unity still reports itself as focused. It now returns a frame counter: call it
twice and compare.

### Documentation honesty

- The project is described as **source-available**, not open-source. It is
  MIT + Commons Clause, which restricts commercial use and therefore is not
  open-source under the OSI definition. The licence section was already correct;
  a one-line summary elsewhere contradicted it.
- Our own clarifying paragraph in `LICENSE` moved out of the Commons Clause text
  and is now labelled as a clarification, so the standard condition reads
  verbatim.
- The `~/.unity_architect_ai` paths now state why the old name survives: they are
  the address of your existing encryption key and database, and renaming them
  would make already-saved API keys undecryptable.

### New demo

The README recording is current again — one prompt builds a course in Unity, a
second hands the game to the agent, and the player cube walks and jumps its way
to the top step. 8.16 MB → 1.12 MB.

## v3.0.1 — 8 Ağustos 2026

Three fixes on top of v3.0.0; the first one blocked the Claude path entirely on
most Windows installs.

### 🔧 Claude Code would not start on Windows
- v3.0.0 stopped bundling the CLI, so the SDK falls back to PATH — where npm puts
  only a `claude.cmd` shim, and the SDK **refuses** `.cmd` (cmd.exe can execute
  commands injected through arguments). Session never opened:
  `Refusing to execute batch script '...\claude.CMD'`.
- The shim carries its target in plain text; the app now reads it and passes the
  real executable as `ClaudeAgentOptions(cli_path=)`. Measured here: resolves to
  `claude.exe` 2.1.226, which PATH never exposed.
- ⚠️ Recorded: the chat gate did **not** catch this. It asks "is a claude binary
  installed" and the shim answers yes; the SDK needs something it can *execute*.
  Two different questions with one name.

### 🧠 Session continuity
- **`resume`**: the CLI's own session is resumed when possible. It keeps the full
  transcript on disk; only the id was missing. Stored per (conversation, CLI
  family) with the workspace — a mismatch is ignored, because CLI sessions are
  keyed by project directory and resuming elsewhere would show **another
  project's** history.
- When a summary is still needed (agent switch, session gone), **the cut is now
  marked**. Previously the budget filled and older messages were dropped with a
  bare `break`; the model got a transcript starting mid-conversation and could not
  know. Measured: 17 of 48 messages survived, **71% of characters lost, silently**.
- Resuming does **not** also inject the transcript — that would show the model the
  same conversation twice.

### 🧪 Gates
backend **1127** · frontend **406** · tsc **0**

## v3.0.0 — 8 Ağustos 2026

**Unity Architect AI → Gamachine.** Major version, because this is not an upgrade
installed over the old one, and two behaviours changed deliberately.

### 🏷 Rename
- Product, `appId`, package name, window titles, repository and release pages.
- ⚠️ The old install is **not** removed automatically (`appId` changed), and an
  installed v2.3.1 gets **no** update notification. The release notes are the only
  announcement channel.
- `~/.unity_architect_ai` deliberately **unchanged** — it holds the key the API
  keys are encrypted with; renaming it would make them permanently unreadable.
  Same reasoning for the keyring service name and the markers written into the
  user's own files.
- "Unity" could not lead a product name under Unity's trademark guidelines; the
  new name is engine-neutral so Unreal/Godot support would not force a second
  rename.

### 🔌 The bundled Claude Code CLI was removed
- The SDK vendors its own copy and packaging swept it in — nobody chose it, and it
  **took priority over the user's own installation**, so their Claude Code was
  never used.
- Installer **561 → 308 MB** (−253 MB, 45%), measured from a rebuilt package.
- Consequence: the Claude path now needs Claude Code installed by the user.

### 🔒 Chat is gated on a usable provider
- New `GET /provider-ready`: cloud → has a key, CLI → installed (and signed in
  where that is measurable), Ollama → service reachable.
- The composer is disabled until then; previously the first reply could be a raw
  Python traceback.
- Fail-**open** when readiness cannot be measured: an unreachable backend does not
  mean a missing provider, and locking there would reproduce the very problem the
  gate exists to prevent.
- `loggedIn == null` means *not measured*, not *not logged in* — only a measured
  `false` blocks.

### 🌍 Internationalisation
- Starting language now derives from the OS. The old hard-coded `tr` also reached
  the model, so an English question came back in Turkish.
- Dictionary **157 → 373** keys; the whole renderer goes through it.
- Still Turkish: Electron main-process dialogs (37 strings, no dictionary access)
  and backend messages (~301, no mechanism).

### ⚖️ Licensing, privacy
- `LICENSE` + `THIRD-PARTY-NOTICES.md` are now **inside the installer** — they were
  never copied, while FFmpeg (which requires it) was shipped.
- FFmpeg licence stated **per platform** (Windows LGPL, macOS/Linux GPL) with the
  Windows source link added; it previously claimed GPL everywhere.
- Bundled .NET corrected: it is the **SDK** under Microsoft's terms, not MIT.
- Inherited MCP telemetry to a third-party endpoint **disabled**; it was on by
  default and undisclosed.

### 🐛 Fixes
- Codex error path leaked unredacted exception text to the UI (can carry the local
  MCP key); the Claude path already redacted, the sibling did not.
- Chat placeholder read "Ask zap a question…" (template leftover).
- Dead auth screens removed, which let the CSP drop its last remote image source.

### 🧪 Gates
backend **1111** · frontend **406** · tsc **0**


## v2.3.1 — 7 Ağustos 2026

Sohbete fotoğraf yapıştırınca oturumun düşmesi düzeltildi; ayrıca AI artık
Unity'de çalışan oyuna girdi gönderebiliyor.

### 🖼 Düzeltme — yapıştırılan görsel oturumu öldürüyordu
- Belirti boyuta bağlıydı, adede değil: iki fotoğrafla düşüyor, üçle düşmüyordu.
- Sebep: diske yazılan görseli model `Read` ile açınca sonuç base64 olarak tek bir
  satırda geri geliyor; o satırın 1 MB tavanı aşılınca hata kırpılmıyor, **oturum
  komple düşüyordu**. base64 ham boyutun ~4/3'ü olduğundan 750 KB'lık bir fotoğraf
  bile yetiyordu.
- İki katmanlı düzeltme: satır tavanı diğer CLI yoluyla hizalandı **ve** asıl sınır
  kaynağa kondu — büyük görseller diske yazılmadan önce küçültülüyor. Token
  maliyeti de düşüyor.
- Şeffaf PNG'lerde alfa kanalı korunuyor (ilk düzeltme denemesi onları siyah kareye
  çeviriyordu; denetim turu yakaladı).

### 🎮 Yeni — `manage_input`: AI oyunu oynayabiliyor
- Çalışan oyuna klavye, fare, gamepad ve UI girdisi gönderiliyor. Girdi Unity Input
  System'in sanal cihazlarına sürecin içinden basıldığı için **pencere odağı
  gerekmiyor**.
- Aksiyonlar: `describe`, `key`, `mouse_move`, `mouse_button`, `scroll`, `gamepad`,
  `ui_click`, `sequence`, `reset`.
- ⚠️ Yalnız yeni Input System'e göre yazılmış oyun kodu bu olayları görür; eski
  `Input.GetKey` kullanan projelerde çalışan tek yol `ui_click`'tir.

### 📸 Düzeltme — ekran görüntüsü eylem adı
- Modele var olmayan bir eylem adı öğretiliyordu; ekran görüntüsü istekleri bu
  yüzden boşa düşebiliyordu.

### 📖 Dokümantasyon
- README (TR + EN) 105 commit'lik gerçeklikle hizalandı: unityMCP onay davranışı
  artık sağlayıcı bazında doğru anlatılıyor, araç tablosu 46 aracın tamamını
  kapsıyor, eksik üç CLI sağlayıcısı (Cursor, OpenCode, Kimi Code) eklendi, model
  listeleri güncellendi ve gömülü .NET'in **SDK** olduğu (runtime değil) gerekçesiyle
  yazıldı.

---

## v2.3.0 — 2 Ağustos 2026

**Bu sürüm bir güvenlik sürümüdür.** v2.2.0'dan bu yana 125 commit geldi ve
100'ü düzeltme; ağırlığı, ürünün sırlarını, onay kapısını ve dosya erişimini
sertleştiren çalışma oluşturuyor. v2.2.0 kullanan herkesin güncellemesi
öneriliyor.

### 🔐 Güvenlik

**Yerel sır (backend ↔ Unity MCP paylaşımlı anahtarı)**
- Sır artık URL'de değil `X-API-Key` başlığında taşınıyor. Eskiden adres
  çubuğuna, log satırlarına ve süreç listelerine düşebiliyordu.
- Sır hiçbir CLI yapılandırma dosyasına yazılmıyor.
- Token dosyası Windows'ta ACL ile kilitli, yazımlar atomik; kimlik doğrulaması
  yola değil **açılmış dosya tanıtıcısına** bakıyor (sembolik bağ/junction ile
  yönlendirme kapandı).
- Sırrın hem yeni hem eski biçimi loglarda maskeleniyor.

**Prompt ve komut satırı**
- Kullanıcı prompt'u artık süreç argümanlarında taşınmıyor. Eskiden makinedeki
  herhangi bir süreç süreç listesinden prompt'un tamamını okuyabiliyordu.
- `[CMD]` kaydı prompt'un tamamını kalıcı bir dosyaya yazmıyor.

**Onay kapısı**
- Kapı Unity MCP boğazına kondu: **dokuz sağlayıcının dokuzu da** artık aynı
  kapıdan geçiyor. Öncesinde araç çağrıları kapıyı hiç görmüyordu.
- Kapı REST rotası üzerinden de atlatılamıyor.
- `delete_file` kapıya alındı.
- **Yazma onay kartı artık ne yazılacağını gösteriyor** — kart, yetkilendirilen
  girdinin tamamını taşıyor; öncesinde göremediğin bir şeyi onaylıyordun.
- Kart hangi projenin değişeceğini söylüyor; eşzamanlı adım turlarında
  otomatik onay "en az biri" değil "hepsi" kuralına bağlandı.
- Kullanıcının açtığı bir proje kapıyı devre dışı bırakamıyor.
- Codex onay hakemi `user` olarak sabitlendi ve yanıttan doğrulanıyor: onay
  isteği artık bir dil modeline devredilemiyor.

**Masaüstü uygulaması**
- **İçerik Güvenliği Politikası (CSP)** eklendi; Monaco editörü CDN yerine
  yerelden servis ediliyor — uygulama artık çalışmak için dış bir sunucuya
  bağlanmıyor.
- IPC çağrıları için kaynak kapısı: yalnız uygulamanın kendi sayfası çağırabilir.
- Workspace kökü yalnızca kullanıcının native diyalogla seçtiği bir yol olabilir.
- Uygulama uzak bir sayfaya gidemiyor, yeni pencere açamıyor, `<webview>`
  ekleyemiyor; dış linkler işletim sisteminin tarayıcısına gidiyor.

**Dosya erişimi**
- Sembolik bağ, junction, **sabit bağ** ve NTFS alternatif veri akışı yoluyla
  workspace dışına çıkma yolları kapatıldı.
- Okuma kapısında kontrol/kullanım yarışı kapatıldı: kapının onayladığı dosya
  ile okunan dosya artık aynı olmak zorunda, ve bu açılmış tanıtıcının
  kimliğiyle doğrulanıyor.
- Yapılandırma yazımları workspace dışındaki bir dosyanın üstüne yazamıyor.

**Diğer**
- Komut onay kapısındaki ön ek eşleşme atlatması kapatıldı.
- Ortam değişkeni sızıntısı sınıfı kapatıldı (ad eşleşmesi değil **değer**
  eşleşmesi).
- İndirilen tüm ikililer (OmniSharp, .NET SDK, uv, ffmpeg, yt-dlp) sabitlenmiş
  bir kütüğe ve özet doğrulamasına bağlandı.
- Kullanıcı projesine yazılan yapılandırma dosyaları `.gitignore`'a alındı.

### ✨ Yenilikler

- **Claude Opus 5** desteği.
- **Kimi K3 / Kimi CLI** sağlayıcısı.
- **Gemini 3.6** ve **Gemini 3.5 Lite**.
- OmniSharp için **.NET SDK pakete gömüldü** (macOS/Linux) — sıfır kurulum.
- Unity MCP: N+1 sorgu iyileştirmesi, kısmi eşleşme, toplu işlem zincirleme,
  kota/round-trip/no-op davranışları.

### 🐛 Düzeltmeler

- **Sohbetteki dosya linki artık dosyayı açıyor.** Yeşil dosya adına
  tıklayınca uygulama "resetleniyor" gibi görünüyordu — aslında pencere o
  adrese gidip arayüzü boşaltıyordu.
- **Beklenmedik veri artık tüm pencereyi boşaltmıyor:** uygulamaya bir hata
  sınırı eklendi, hata beyaz ekran yerine okunabilir bir panel gösteriyor.
- Model listesi bayat bir kapanış değeri yüzünden tüm API modellerini
  gizleyebiliyordu.
- Unity MCP, Editor'da domain reload sonrası yeniden bağlanmayı sürdürüyor.
- C# projesi (`csproj`) üretimi artık harici bir IDE kurulu olmasına bağlı değil.
- C# hover'ının asılması giderildi.
- `execute_code`'un atlatılabildiği yer düzeltildi.
- Windows'ta ürünün tamamını çalışmaz hale getirebilen üç hata giderildi.
- Uygulamanın kendi bağlantı afişi kendi onay kapısına takılıyordu.

### 📄 Lisans

- Proje **MIT + Commons Clause** ile lisanslandı; üçüncü parti bildirimleri eklendi.

### 🧪 Kalite

- Unity MCP sunucu test suite'i (1522 test) kalite kapısına bağlandı.
- Testler Windows'ta koşabilir hale getirildi; bu çalışma üç ürün hatası ortaya
  çıkardı.
- Dört bağımsız denetim turu koşuldu (biri tamamen dış gözle); üretilen
  bulguların tamamı kanıtlanabilir probe'larla üretildi ve kapatıldı.

### ⚠️ Bilinenler

- macOS derlemesi yalnız **Apple Silicon (arm64)**.
- Otomatik güncelleme **yalnız bildirim** yapar; indirme ve kurulum kullanıcıya
  bırakılır (uygulama imzasız olduğu için sessiz kurulum bilerek kapalı).
