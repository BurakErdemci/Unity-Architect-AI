"""OmniSharp sidecar yaşam döngüsü. unity_mcp_manager deseninde: workspace
açılınca spawn, workspace değişince restart, kapanışta kill. Tüm satır/kolon
çevirileri BURADA yapılır: LSP 0 tabanlı ↔ bizim format 1 tabanlı."""
import asyncio
import logging
import os
import platform
import sys
import time
import urllib.parse
import urllib.request

from .lsp_client import LspClient, LspError

logger = logging.getLogger("OmniSharp")

_SEVERITY = {1: "error", 2: "warning", 3: "info", 4: "hint"}


def _norm_key(path: str) -> str:
    """Diagnostics sözlüğü anahtarı: URI'den gelen yol (C:/eğik/çizgi) ile
    os.path.abspath çıktısı (C:\\ters\\çizgi) Windows'ta eşleşmez — ikisini de
    normalize et (normpath + normcase), yoksa diagnostics hep boş görünür."""
    return os.path.normcase(os.path.normpath(path))


def _path_to_uri(path: str) -> str:
    return "file:///" + urllib.parse.quote(path.replace("\\", "/").lstrip("/"))


def _uri_to_path(uri: str) -> str:
    p = urllib.parse.unquote(uri)
    p = p[len("file:///"):] if p.startswith("file:///") else p[len("file://"):]
    return p


def _lsp_diag_to_problem(rel_file: str, d: dict) -> dict:
    r = d.get("range") or {}
    start, end = r.get("start") or {}, r.get("end") or {}
    return {
        "file": rel_file,
        "line": int(start.get("line", 0)) + 1,
        "column": int(start.get("character", 0)) + 1,
        "endColumn": int(end.get("character", 0)) + 1,
        "message": d.get("message", ""),
        "severity": _SEVERITY.get(d.get("severity", 1), "error"),
    }


def _omnisharp_roots() -> list[str]:
    """omnisharp kök klasörü adayları: frozen'da resources/omnisharp, dev'de repo third_party/omnisharp."""
    roots = []
    if getattr(sys, "frozen", False):
        roots.append(os.path.abspath(os.path.join(os.path.dirname(sys.executable), "..", "omnisharp")))
    here = os.path.dirname(os.path.abspath(__file__))          # Backend/app/omnisharp
    repo = os.path.abspath(os.path.join(here, "..", "..", ".."))  # repo kökü
    roots.append(os.path.join(repo, "third_party", "omnisharp"))
    return roots


def _is_apple_silicon() -> bool:
    """Donanım Apple Silicon mı? platform.machine() YETMİYOR: Rosetta altında
    koşan bir x86_64 Python 'x86_64' döndürüyor, oysa makine arm64 ve arm64
    binary'si sorunsuz spawn edilir (subprocess, in-process yüklenmiyor).
    Kernel sürüm dizesi Rosetta'da bile çevrilmiyor — ölçüldü 2026-07-27:
    `arch -x86_64 python3` → machine='x86_64', uname().version '…RELEASE_ARM64_T8132'."""
    if platform.machine().lower() in ("arm64", "aarch64"):
        return True
    try:
        return "ARM64" in os.uname().version.upper()
    except AttributeError:      # os.uname yok (Windows) — buraya düşmemeli
        return False


def _platform_key() -> str | None:
    """Bu makine için OmniSharp asset klasör adı; desteklenmiyorsa None.

    Adlar UYDURULMUYOR: tek kaynak scripts/fetch_omnisharp.py ASSETS sözlüğü —
    orada yalnız win-x64, osx-arm64, linux-x64 var. Özellikle osx-x64 (Intel Mac)
    ve linux-arm64 release'i indirilmiyor; None dönüp çağıranın anlaşılır hata
    vermesini sağlıyoruz, yoksa var olmayan bir yol denenip "binary bulunamadı"
    gibi yanıltıcı bir mesaj çıkıyor."""
    if os.name == "nt" or sys.platform.startswith("win"):
        # win-arm64 release'i yok; ARM Windows x64'ü emüle ettiği için win-x64 doğru.
        return "win-x64"
    if sys.platform == "darwin":
        return "osx-arm64" if _is_apple_silicon() else None
    if sys.platform.startswith("linux"):
        return "linux-x64" if platform.machine().lower() in ("x86_64", "amd64") else None
    return None


def _unsupported_reason() -> str:
    """Desteklenmeyen platform için kullanıcıya gösterilecek somut sebep."""
    return (f"OmniSharp bu platform için dağıtılmıyor: {sys.platform}/{platform.machine()}. "
            f"Desteklenen: Windows x64, macOS Apple Silicon, Linux x64. "
            f"C# analizi (hata denetimi, IntelliSense) devre dışı; diğer özellikler çalışır.")


def _resolve_binary() -> str | None:
    plat = _platform_key()
    if plat is None:
        return None
    exe = "OmniSharp.exe" if plat.startswith("win") else "OmniSharp"
    for root in _omnisharp_roots():
        cand = os.path.join(root, plat, exe)
        if os.path.exists(cand):
            return cand
    return None


def _spawn_env() -> dict | None:
    """OmniSharp spawn ortamı. macOS/Linux'ta GÖMÜLÜ .NET runtime'a yönlendirir
    (0-kurulum: kullanıcının PC'sinde .NET olmasa da çalışır). OmniSharp net6.0
    hedefli → DOTNET_ROLL_FORWARD=Major ile gömülü .NET 10 LTS'te koşar (canlı
    LSP initialize testiyle doğrulandı). Windows net472 → dokunma (None = parent env)."""
    plat = _platform_key()
    if plat is None or plat.startswith("win"):
        return None
    # dotnet-<plat> klasör adı _platform_key ile aynı anahtarı kullanıyor
    # (fetch_omnisharp.fetch_dotnet da öyle yazıyor) — sabit string yazmak, Intel
    # Mac'te var olmayan bir dotnet-linux-x64 yolunu aramaya yol açıyordu.
    for root in _omnisharp_roots():
        dotnet_root = os.path.join(root, f"dotnet-{plat}")
        if os.path.exists(os.path.join(dotnet_root, "dotnet")):
            return {**os.environ,
                    "DOTNET_ROOT": dotnet_root,
                    "DOTNET_ROLL_FORWARD": "Major"}
    # Gömülü runtime yoksa eski davranış: sistemdeki .NET'e güven (varsa)
    return None


class OmniSharpManager:
    def __init__(self):
        self._client: LspClient | None = None
        self._workspace: str | None = None
        self._opened: set[str] = set()
        self._diags: dict[str, list[dict]] = {}   # abs path → problems (eski format)
        self._diag_ping: dict[str, float] = {}    # abs path → son yayın zamanı
        self.status = {"state": "off", "detail": ""}
        self._lock = asyncio.Lock()

    # ── yaşam döngüsü ────────────────────────────────────────────────
    async def ensure_started(self, workspace: str) -> None:
        async with self._lock:
            if self._workspace == workspace and self._client and self._client.alive:
                return
            await self._stop_locked()
            binary = _resolve_binary()
            if not binary:
                # İki ayrı arıza — kullanıcıya farklı şey söylemeli: platform hiç
                # desteklenmiyor (yapılacak bir şey yok) vs. binary indirilmemiş
                # (fetch script'i koşturulunca düzelir).
                if _platform_key() is None:
                    detail = _unsupported_reason()
                else:
                    detail = "OmniSharp binary bulunamadı (scripts/fetch_omnisharp.py koşuldu mu?)"
                self.status = {"state": "error", "detail": detail}
                logger.error("%s", detail)
                return
            self.status = {"state": "starting", "detail": "C# analizi hazırlanıyor…"}
            self._workspace = workspace
            self._maybe_sync_csproj(workspace)
            client = LspClient()
            # Bayrak adları Task 1 Step 3'te doğrulandı (--help çıktısına göre güncel)
            cmd = [binary, "-z", "-s", workspace, "--languageserver", "--encoding", "utf-8"]
            try:
                await client.start(cmd, cwd=workspace, env=_spawn_env())
                client.on_notification("textDocument/publishDiagnostics", self._on_diags)
                await client.request("initialize", {
                    "processId": os.getpid(),
                    "rootUri": _path_to_uri(workspace),
                    "capabilities": {"textDocument": {
                        "synchronization": {"didSave": False},
                        "publishDiagnostics": {},
                        "completion": {"completionItem": {"snippetSupport": False}},
                        "hover": {"contentFormat": ["markdown", "plaintext"]},
                    }},
                }, timeout=120)
                client.notify("initialized", {})
                self._client = client
                self.status = {"state": "ready", "detail": ""}
                logger.info("OmniSharp hazır: %s", workspace)
            except Exception as e:
                self.status = {"state": "error", "detail": str(e)[:200]}
                logger.exception("OmniSharp başlatılamadı")
                await client.stop()

    def _maybe_sync_csproj(self, workspace: str) -> None:
        """Workspace'te .sln yoksa Unity'den üretmeyi dene (MCP REST, best-effort)."""
        try:
            has_sln = any(f.endswith(".sln") for f in os.listdir(workspace))
        except OSError:
            has_sln = True
        if has_sln:
            return
        try:
            # /api/command paylaşımlı sır ister (sırsız çağrı 401). Sır sunucuyu
            # başlatan manager'da tutuluyor; import döngüsüne girmemek için yerel import.
            from ..unity_ai_mcp.unity_mcp_manager import unity_mcp_manager
            req = urllib.request.Request(
                "http://localhost:8080/api/command", method="POST",
                data=b'{"type": "manage_editor", "params": {"action": "sync_csproj"}}',
                headers={"Content-Type": "application/json",
                         **unity_mcp_manager.api_headers()})
            urllib.request.urlopen(req, timeout=15)
            logger.info("sync_csproj tetiklendi (.sln yoktu)")
        except Exception:
            logger.info(".sln yok ve Unity'ye ulaşılamadı — 'Unity'yi bir kez aç' durumu")

    async def stop(self) -> None:
        async with self._lock:
            await self._stop_locked()

    async def _stop_locked(self) -> None:
        if self._client:
            await self._client.stop()
        self._client = None
        self._opened.clear()
        self._diags.clear()
        self.status = {"state": "off", "detail": ""}

    # ── diagnostics ──────────────────────────────────────────────────
    def _on_diags(self, params: dict) -> None:
        path = _uri_to_path(params.get("uri", ""))
        rel = os.path.relpath(path, self._workspace).replace("\\", "/") if self._workspace else path
        key = _norm_key(path)
        self._diags[key] = [_lsp_diag_to_problem(rel, d) for d in params.get("diagnostics") or []]
        self._diag_ping[key] = time.monotonic()

    def diagnostics_for(self, path: str) -> list[dict]:
        return self._diags.get(_norm_key(os.path.abspath(path)), [])

    async def sync_document(self, path: str, text: str) -> list[dict]:
        if not (self._client and self._client.alive):
            return []
        apath = os.path.abspath(path)
        uri = _path_to_uri(apath)
        if apath not in self._opened:
            self._opened.add(apath)
            self._client.notify("textDocument/didOpen", {"textDocument": {
                "uri": uri, "languageId": "csharp", "version": 1, "text": text}})
        else:
            self._client.notify("textDocument/didChange", {
                "textDocument": {"uri": uri, "version": int(time.time())},
                "contentChanges": [{"text": text}]})
        # publishDiagnostics async gelir → kısa pencere bekle (yeni yayın ya da timeout)
        sent = time.monotonic()
        key = _norm_key(apath)
        for _ in range(24):  # ~1.2 sn
            await asyncio.sleep(0.05)
            if self._diag_ping.get(key, 0) >= sent:
                break
        return self.diagnostics_for(apath)

    # ── IntelliSense ─────────────────────────────────────────────────
    def _doc_pos(self, path: str, line: int, column: int) -> dict:
        return {"textDocument": {"uri": _path_to_uri(os.path.abspath(path))},
                "position": {"line": line - 1, "character": column - 1}}

    async def completion(self, path: str, text: str, line: int, column: int) -> list[dict]:
        await self.sync_document(path, text)
        try:
            res = await self._client.request("textDocument/completion",
                                             self._doc_pos(path, line, column), timeout=10)
        except LspError:
            return []
        items = res.get("items", res) if isinstance(res, dict) else (res or [])
        out = []
        for it in items[:200]:
            out.append({"label": it.get("label", ""), "kind": it.get("kind", 1),
                        "insertText": it.get("insertText") or it.get("label", ""),
                        "detail": it.get("detail") or ""})
        return out

    async def hover(self, path: str, text: str, line: int, column: int) -> str | None:
        await self.sync_document(path, text)
        try:
            res = await self._client.request("textDocument/hover",
                                             self._doc_pos(path, line, column), timeout=10)
        except LspError:
            return None
        if not res:
            return None
        c = res.get("contents")
        if isinstance(c, dict):
            return c.get("value")
        if isinstance(c, list):
            return "\n\n".join(x.get("value", x) if isinstance(x, dict) else str(x) for x in c)
        return str(c) if c else None

    async def definition(self, path: str, text: str, line: int, column: int) -> dict | None:
        await self.sync_document(path, text)
        try:
            res = await self._client.request("textDocument/definition",
                                             self._doc_pos(path, line, column), timeout=10)
        except LspError:
            return None
        loc = (res[0] if isinstance(res, list) and res else res) or None
        if not loc or "uri" not in loc:
            return None
        start = (loc.get("range") or {}).get("start") or {}
        return {"file": _uri_to_path(loc["uri"]),
                "line": int(start.get("line", 0)) + 1,
                "column": int(start.get("character", 0)) + 1}


_manager: OmniSharpManager | None = None


def get_omnisharp_manager() -> OmniSharpManager:
    global _manager
    if _manager is None:
        _manager = OmniSharpManager()
    return _manager
