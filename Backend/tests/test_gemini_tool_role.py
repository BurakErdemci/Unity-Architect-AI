"""Gemini yolunda araç sonucunun taşındığı ROL.

Saha arızası, 30 Ağu 2026: Gemini API modeliyle bir araç çağrıldığı anda tur
ölüyordu —

    400 INVALID_ARGUMENT — "Role 'tool' is not supported. Please use a valid
    role: SYSTEM, SYSTEM_1, USER, ASSISTANT, DEVELOPER, CONTEXT,
    USER_CONTEXT, MODEL, USER."

`role="tool"` OpenAI'ın konvansiyonu; Google'ın SDK'sı araç sonuçlarını
`types.Content(role='user', ...)` ile sarıyor (`google/genai/models.py`,
otomatik fonksiyon çağırma dalı). Satır 30 May 2026'dan beri yanlıştı ve
sessiz kaldı, çünkü hiçbir test araca kadar gitmiyordu: mevcut testler döngü
sayısını ölçüyordu, GÖNDERİLEN GÖVDEYİ değil.

Bedeli ölçülebilir: bu yolun araçlı hali hiç çalışmadı, ve aynı yolda yapılan
iterasyon-tavanı düzeltmesi de bu yüzden üründe hiç denenemedi.

Bu test o gövdeyi ölçüyor — sahte istemci `contents`i kaydediyor ve rol
üzerinden hüküm veriliyor. Sahte, GERÇEK `google.genai.types` nesneleri
alıyor, yani rolü tipin kendisi de doğruluyor.
"""
import asyncio
import os
import sys
import types
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import agentic.agent_runner as ar


class _KaydedenGemini:
    """İlk turda araç çağırır, ikincide biter; her çağrının `contents`ini saklar."""

    def __init__(self):
        self.calls = 0
        self.gonderilen = []
        self.models = types.SimpleNamespace(generate_content=self._generate)

    def _generate(self, **kwargs):
        self.gonderilen.append(kwargs.get("contents"))
        i = self.calls
        self.calls += 1
        if i == 0:
            parts = [types.SimpleNamespace(
                function_call=types.SimpleNamespace(name="read_file", args={"path": "a.cs"}),
                text=None, thought=False)]
        else:
            parts = [types.SimpleNamespace(function_call=None, text="bitti", thought=False)]
        return types.SimpleNamespace(
            candidates=[types.SimpleNamespace(content=types.SimpleNamespace(parts=parts))],
            usage_metadata=types.SimpleNamespace(prompt_token_count=1, candidates_token_count=1),
        )


async def _uyuma(_s):
    return None


def _kostur():
    client = _KaydedenGemini()
    runner = ar.AgentRunner(provider_type="google", api_key="k", model_name="m",
                            workspace_path=".")
    patches = [
        mock.patch.object(ar, "execute_tool",
                          lambda name, args, workspace, conversation_id: {"success": True, "summary": "ok"}),
        mock.patch.object(ar, "_all_tool_definitions",
                          lambda: [{"name": "read_file", "description": "d",
                                    "parameters": {"type": "object", "properties": {}}}]),
        mock.patch.object(ar, "get_gemini_tool_declarations",
                          lambda: [{"function_declarations": []}]),
        mock.patch.object(ar.asyncio, "sleep", _uyuma),
        mock.patch.object(ar.genai, "Client", lambda **kw: client),
    ]

    async def _go():
        return [e async for e in runner._run_inner("merhaba")]

    for p in patches:
        p.start()
    try:
        olaylar = asyncio.run(_go())
    finally:
        for p in reversed(patches):
            p.stop()
    return client, olaylar


def _roller(gonderilen):
    """Son çağrıda giden bütün Content rolleri."""
    son = gonderilen[-1] or []
    return [getattr(c, "role", None) for c in son]


def _arac_sonucu_tasiyan_roller(gonderilen):
    """YALNIZ araç sonucu taşıyan Content'lerin rolleri.

    "user" rolünün varlığına bakmak yetmiyor: kullanıcının kendi mesajı da o
    rolde, o yüzden rol yanlışken bile geçen bir test olurdu — ölçüldü, ilk
    sürüm tam olarak öyleydi ve mutasyon turunda ortaya çıktı.
    """
    son = gonderilen[-1] or []
    roller = []
    for c in son:
        parcalar = getattr(c, "parts", None) or []
        if any(getattr(p, "function_response", None) is not None for p in parcalar):
            roller.append(getattr(c, "role", None))
    return roller


def test_the_tool_result_never_rides_on_the_tool_role():
    # Uç bu rolü reddediyor. Testin adı budur ve tek başına da hüküm verir.
    client, _ = _kostur()
    assert "tool" not in _roller(client.gonderilen)


def test_the_tool_result_rides_on_the_user_role_like_the_sdk_does():
    client, _ = _kostur()
    tasiyanlar = _arac_sonucu_tasiyan_roller(client.gonderilen)
    assert tasiyanlar, "araç sonucu taşıyan hiçbir Content bulunamadı — test kendi ölçeceği şeyi kaybetmiş"
    assert set(tasiyanlar) == {"user"}


def test_the_turn_actually_reaches_a_second_call():
    # Rol yanlışsa gerçek uçta ikinci çağrı HİÇ olmuyordu (400 ile ölüyordu).
    # Sahte uç 400 atmıyor, o yüzden bu test tek başına yeterli değil —
    # yukarıdaki iki rol iddiasının anlamlı olabilmesi için döngünün araca
    # kadar gittiğini sabitliyor.
    client, olaylar = _kostur()
    assert client.calls == 2
    assert any(e.type == "tool_result" for e in olaylar)


def test_the_turn_ends_normally_rather_than_with_an_error():
    _, olaylar = _kostur()
    tipler = [e.type for e in olaylar]
    assert "done" in tipler
    assert "error" not in tipler
