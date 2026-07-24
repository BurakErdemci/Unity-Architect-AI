"""OpenCode MCP çağrıları için yalnız aktif tur boyunca geçerli onay politikası.

OpenCode'un proje içindeki ``opencode.json`` dosyası kalıcıdır. Bu nedenle Auto
mod bilgisini doğrudan o dosyaya yazmak, uygulama turu bittikten sonra da yetki
bırakır. Buradaki tek kullanımlık anahtar sadece çalışan AgentRunner turu boyunca
geçerlidir; tur bittiğinde anahtar iptal edilir.
"""

from dataclasses import dataclass
import os
import secrets
import threading


@dataclass(frozen=True)
class _ApprovalTurn:
    workspace_path: str
    auto_approve: bool


_ACTIVE_TURNS: dict[str, _ApprovalTurn] = {}
_LOCK = threading.Lock()


def _canonical_workspace(path: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(path or ".")))


def begin_opencode_turn(workspace_path: str, generation_mode: str) -> str:
    """Yeni bir OpenCode turu kaydeder ve tahmin edilemez geçici anahtar döndürür."""
    token = secrets.token_urlsafe(32)
    turn = _ApprovalTurn(
        workspace_path=_canonical_workspace(workspace_path),
        auto_approve=(generation_mode == "auto"),
    )
    with _LOCK:
        _ACTIVE_TURNS[token] = turn
    return token


def end_opencode_turn(token: str | None) -> None:
    """Tur anahtarını iptal eder. Bilinmeyen/boş anahtarlar güvenle yok sayılır."""
    if not token:
        return
    with _LOCK:
        _ACTIVE_TURNS.pop(token, None)


def should_auto_approve(token: str | None, workspace_path: str) -> bool:
    """Anahtar aktif Auto turuna ve tam olarak aynı workspace'e aitse True döner."""
    if not token:
        return False
    with _LOCK:
        turn = _ACTIVE_TURNS.get(token)
    return bool(
        turn
        and turn.auto_approve
        and turn.workspace_path == _canonical_workspace(workspace_path)
    )
