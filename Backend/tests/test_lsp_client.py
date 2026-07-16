import asyncio
import os
import sys
import textwrap
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from omnisharp.lsp_client import LspClient

# Content-Length frame'li istekleri okuyup echo'layan sahte sunucu
FAKE_SERVER = textwrap.dedent("""
    import json, sys
    def read_msg():
        headers = {}
        while True:
            line = sys.stdin.buffer.readline().decode()
            if line in ("\\r\\n", "\\n"): break
            k, v = line.split(":", 1); headers[k.strip().lower()] = v.strip()
        return json.loads(sys.stdin.buffer.read(int(headers["content-length"])))
    def write_msg(obj):
        body = json.dumps(obj).encode()
        sys.stdout.buffer.write(f"Content-Length: {len(body)}\\r\\n\\r\\n".encode())
        sys.stdout.buffer.write(body); sys.stdout.buffer.flush()
    while True:
        msg = read_msg()
        if msg.get("method") == "exit": break
        if "id" in msg:  # request -> echo params as result
            write_msg({"jsonrpc": "2.0", "id": msg["id"], "result": {"echo": msg.get("params")}})
        elif msg.get("method") == "want/notify":  # notify -> server-initiated notification
            write_msg({"jsonrpc": "2.0", "method": "test/notification", "params": {"ok": True}})
""")


@pytest.mark.asyncio
async def test_request_response_roundtrip(tmp_path):
    server = tmp_path / "fake_server.py"
    server.write_text(FAKE_SERVER, encoding="utf-8")
    c = LspClient()
    await c.start([sys.executable, str(server)], cwd=str(tmp_path))
    result = await c.request("test/method", {"x": 1})
    assert result == {"echo": {"x": 1}}
    got = asyncio.Event()
    c.on_notification("test/notification", lambda p: got.set())
    c.notify("want/notify", {})
    await asyncio.wait_for(got.wait(), 5)
    await c.stop()
    assert not c.alive
