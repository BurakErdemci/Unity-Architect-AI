#!/usr/bin/env python3
"""
stdio <-> streamable-HTTP MCP köprüsü — SADECE Codex için.

Neden var: Codex 0.14x, yerel FastMCP streamable-HTTP MCP sunucularına (unityMCP)
bağlanmayı bozdu (önce OAuth discovery yapıp initialize'a varmadan düşüyor;
openai/codex issue #26955, #26072). Codex'in STDIO transport'u ise sağlam çalışıyor.
Bu köprü: Codex ile stdio (newline-delimited JSON-RPC) konuşur, mesajları mevcut
unityMCP HTTP sunucusuna (streamable-http) forward eder. İKİNCİ bir Unity bağlantısı
AÇMAZ — tek HTTP sunucusunu paylaşır. OAuth yok.

Kullanım:  UNITY_MCP_URL=http://127.0.0.1:8080/mcp python codex_unitymcp_bridge.py

Kapsam (v1): client-initiated request/response + notification akışı (initialize,
tools/list, tools/call, resources/*, prompts/* ...). Bu, Codex'in tool kullanımını
tam karşılar. Server-initiated push (uzun işlerde progress notification) v1'de
köprülenmez — unityMCP tool'ları senkron olduğu için pratikte etkisiz.
"""
import os
import sys
import json
import urllib.request
import urllib.error

DEFAULT_URL = "http://127.0.0.1:8080/mcp"


def _read_shared_secret():
    """Paylaşımlı sırrı doğrudan token dosyasından okur.

    Neden ortam/argv değil: bu köprü sunucuyla AYNI makinede, AYNI kullanıcıyla
    koşuyor, yani dosyayı zaten okuyabiliyor. Sırrı config'e ya da komut satırına
    koymak onu `ps` çıktısına, `.mcp.json`'a ve hata loglarına taşıyordu — bir
    denetimin dört ayrı bulgusu bundan çıktı. Dosyadan okumak o yolların hepsini
    kapatıyor ve fazladan hiçbir yetki vermiyor.
    """
    path = os.path.join(os.path.expanduser("~"), ".unity-mcp", "local-api-token")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


class Bridge:
    def __init__(self, url):
        self.url = url
        self.session_id = None
        self.api_key = _read_shared_secret()

    def _post(self, message):
        """Tek JSON-RPC mesajını HTTP'ye POST eder; JSON-RPC yanıt(lar)ını
        (dict listesi) döndürür. Notification/202 için boş liste döner."""
        data = json.dumps(message).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
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
    # URL artık sır TAŞIMIYOR (sır X-API-Key başlığında, token dosyasından
    # okunuyor), yani ortam/argv üzerinden gelmesi bir sızıntı değil.
    url = os.environ.get("UNITY_MCP_URL") or (
        sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    )
    Bridge(url).run()


if __name__ == "__main__":
    main()
