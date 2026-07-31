"""
Execute arbitrary C# code inside the Unity Editor.

Supports execute, history, replay, and clear actions with basic blocked-pattern
checks. Code is compiled by Unity's own compiler (AssemblyBuilder) — same C#
language version as the project, references resolved by Unity.

WARNING: This tool runs arbitrary code in the Unity Editor process.
Safety checks block known dangerous patterns but are NOT a security sandbox.
"""
from typing import Annotated, Any, Literal

from fastmcp import Context
from mcp.types import ToolAnnotations

from services.registry import mcp_for_unity_tool
from services.tools import get_unity_instance_from_context
from transport.unity_transport import send_with_unity_instance
from transport.legacy.unity_connection import async_send_command_with_retry


@mcp_for_unity_tool(
    description=(
        "Execute arbitrary C# code inside the Unity Editor. "
        "The code runs as a method body with access to UnityEngine and UnityEditor namespaces. "
        "Use 'return' to send data back. Compiled by Unity's own compiler — "
        "same C# language version as the project, full access to project types. "
        "Actions: execute (run code), get_history (list past executions), "
        "replay (re-run a history entry), clear_history."
    ),
    # Buradan "NOTE: safety_checks ... is not a full sandbox" cümlesi KALDIRILDI.
    # Canlı testte ölçüldü (31 Tem 2026): engellenen bir desenle karşılaşan model
    # doğrudan `safety_checks: false` önerdi. Sebep hata mesajı değildi — o zaten
    # düzeltilmişti — ŞEMANIN kendisiydi. Hata mesajı yalnız engellendiğinde
    # görünür, şema HER çağrıda okunuyor; yani daha güçlü bir öğretme yüzeyi.
    # "Tam bir kum havuzu değil" uyarısı geliştirici için doğru ve değerli, ama
    # yeri modelin okuduğu metin değil, bu yorum.
    group="scripting_ext",
    annotations=ToolAnnotations(
        title="Execute Code",
        destructiveHint=True,
    ),
)
async def execute_code(
    ctx: Context,
    action: Annotated[
        Literal["execute", "get_history", "replay", "clear_history"],
        "Action to perform.",
    ],
    code: Annotated[
        str,
        "C# code to execute (for 'execute' action). Must be a valid method body. "
        "Access UnityEngine and UnityEditor namespaces. Use 'return' to send data back.",
    ] | None = None,
    # Açıklama modele KOMUT veriyor, bilgi vermiyor. Eski hali engellenen
    # desenlerin listesini ve "advanced bypass is possible" cümlesini taşıyordu;
    # yani modele hem neyin engellendiğini hem de nasıl aşılacağını söylüyordu.
    # Bir savunmanın parametre açıklaması, o savunmanın kullanım kılavuzu olamaz.
    safety_checks: Annotated[
        bool,
        "Leave at the default. Turning this off is the human operator's decision, "
        "not a way around a blocked pattern: if a pattern is blocked, rewrite the "
        "code without it or ask the user.",
    ] = True,
    index: Annotated[
        int,
        "History entry index to replay (for 'replay' action).",
    ] | None = None,
    limit: Annotated[
        int,
        "Number of history entries to return (for 'get_history' action, 1-50). Default: 10.",
    ] = 10,
) -> dict[str, Any]:
    unity_instance = await get_unity_instance_from_context(ctx)

    params_dict: dict[str, Any] = {"action": action}

    if action == "execute":
        if code is None:
            return {"success": False, "message": "Parameter 'code' is required for 'execute' action."}
        params_dict["code"] = code
        params_dict["safety_checks"] = safety_checks
    elif action == "replay":
        if index is None:
            return {"success": False, "message": "Parameter 'index' is required for 'replay' action."}
        params_dict["index"] = index
        # `safety_checks` replay'de de AÇIKÇA gönderiliyor. Eskiden gönderilmiyordu
        # ve C# tarafı geçmişteki değeri miras alıyordu (`ExecuteCode.cs`
        # `HandleReplay` → `entry.safetyChecksEnabled`): bir kez `false` ile
        # koşan kod, sonraki her replay'de sessizce yine kontrolsüz koşuyordu.
        # Onay kartı da bunu gösteremiyordu, çünkü kart yalnız gönderilen
        # parametreleri yazıyor — kullanıcı `action: replay, index: 3` görüp
        # güvenlik kontrollerinin kapalı olduğunu BİLEMİYORDU.
        params_dict["safety_checks"] = safety_checks
    elif action == "get_history":
        params_dict["limit"] = max(1, min(limit, 50))

    params_dict = {k: v for k, v in params_dict.items() if v is not None}

    response = await send_with_unity_instance(
        async_send_command_with_retry,
        unity_instance,
        "execute_code",
        params_dict,
    )

    if not isinstance(response, dict):
        return {"success": False, "message": str(response)}

    return {
        "success": response.get("success", False),
        "message": response.get("message", response.get("error", "")),
        "data": response.get("data"),
    }
