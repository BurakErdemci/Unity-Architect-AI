#!/usr/bin/env python3
"""
stdio <-> streamable-HTTP MCP köprüsü — SADECE Codex için.

Neden var: Codex 0.14x, yerel FastMCP streamable-HTTP MCP sunucularına (unityMCP)
bağlanmayı bozdu (önce OAuth discovery yapıp initialize'a varmadan düşüyor;
openai/codex issue #26955, #26072). Codex'in STDIO transport'u ise sağlam çalışıyor.
Bu köprü: Codex ile stdio (newline-delimited JSON-RPC) konuşur, mesajları mevcut
unityMCP HTTP sunucusuna (streamable-http) forward eder. İKİNCİ bir Unity bağlantısı
AÇMAZ — tek HTTP sunucusunu paylaşır. OAuth yok.

Kullanım:  python codex_unitymcp_bridge.py http://127.0.0.1:8080/mcp

Kapsam (v1): client-initiated request/response + notification akışı (initialize,
tools/list, tools/call, resources/*, prompts/* ...). Bu, Codex'in tool kullanımını
tam karşılar. Server-initiated push (uzun işlerde progress notification) v1'de
köprülenmez — unityMCP tool'ları senkron olduğu için pratikte etkisiz.
"""
import sys
import json
import urllib.request
import urllib.error

DEFAULT_URL = "http://127.0.0.1:8080/mcp"


class Bridge:
    def __init__(self, url):
        self.url = url
        self.session_id = None

    def _post(self, message):
        """Tek JSON-RPC mesajını HTTP'ye POST eder; JSON-RPC yanıt(lar)ını
        (dict listesi) döndürür. Notification/202 için boş liste döner."""
        data = json.dumps(message).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(self.url, data=data, headers=headers, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=180)
        except urllib.error.HTTPError as e:
            resp = e  # hata gövdesini de okuyabilmek için

        sid = resp.headers.get("Mcp-Session-Id")
        if sid:
            self.session_id = sid
        ctype = (resp.headers.get("Content-Type") or "").lower()

        out = []
        if "text/event-stream" in ctype:
            # SSE: her JSON-RPC yanıtı 'data: {...}' satırında. İlk tam yanıt(lar)ı
            # topla; stream request tamamlanınca kapanır.
            for raw in resp:
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    if payload:
                        try:
                            out.append(json.loads(payload))
                        except Exception:
                            pass
        else:
            body = resp.read()
            if body.strip():
                try:
                    out.append(json.loads(body.decode("utf-8", "replace")))
                except Exception:
                    pass
        return out

    def run(self):
        # stdin: newline-delimited JSON-RPC (MCP stdio transport).
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except Exception:
                continue
            is_request = isinstance(message, dict) and message.get("id") is not None
            try:
                responses = self._post(message)
            except Exception as e:
                if is_request:
                    self._emit({
                        "jsonrpc": "2.0",
                        "id": message.get("id"),
                        "error": {"code": -32603, "message": f"bridge error: {e}"},
                    })
                continue
            for r in responses:
                self._emit(r)

    @staticmethod
    def _emit(obj):
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    Bridge(url).run()


if __name__ == "__main__":
    main()
