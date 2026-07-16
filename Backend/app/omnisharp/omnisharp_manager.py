"""OmniSharp sidecar yaşam döngüsü. unity_mcp_manager deseninde: workspace
açılınca spawn, workspace değişince restart, kapanışta kill. Tüm satır/kolon
çevirileri BURADA yapılır: LSP 0 tabanlı ↔ bizim format 1 tabanlı."""
import asyncio
import logging
import os
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


def _resolve_binary() -> str | None:
    """Frozen'da resources/omnisharp, dev'de repo third_party/omnisharp."""
    exe = "OmniSharp.exe" if os.name == "nt" else "OmniSharp"
    plat = "win-x64" if os.name == "nt" else "osx-arm64"
    if getattr(sys, "frozen", False):
        base = os.path.join(os.path.dirname(sys.executable), "..", "omnisharp", plat)
        cand = os.path.abspath(os.path.join(base, exe))
        if os.path.exists(cand):
            return cand
    here = os.path.dirname(os.path.abspath(__file__))          # Backend/app/omnisharp
    repo = os.path.abspath(os.path.join(here, "..", "..", ".."))  # repo kökü
    cand = os.path.join(repo, "third_party", "omnisharp", plat, exe)
    return cand if os.path.exists(cand) else None


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
                self.status = {"state": "error", "detail": "OmniSharp binary bulunamadı"}
                logger.error("OmniSharp binary yok (scripts/fetch_omnisharp.py koşuldu mu?)")
                return
            self.status = {"state": "starting", "detail": "C# analizi hazırlanıyor…"}
            self._workspace = workspace
            self._maybe_sync_csproj(workspace)
            client = LspClient()
            # Bayrak adları Task 1 Step 3'te doğrulandı (--help çıktısına göre güncel)
            cmd = [binary, "-z", "-s", workspace, "--languageserver", "--encoding", "utf-8"]
            try:
                await client.start(cmd, cwd=workspace)
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
            req = urllib.request.Request(
                "http://localhost:8080/api/command", method="POST",
                data=b'{"type": "manage_editor", "params": {"action": "sync_csproj"}}',
                headers={"Content-Type": "application/json"})
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
