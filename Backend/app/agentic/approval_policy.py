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


# ── Ortam turu — anahtar TAŞIYAMAYAN çağıranlar için ────────────────────────
#
# unityMCP sunucusu ayrı bir süreç ve tek kullanımlık tur anahtarını bilemez:
# anahtar ürünün kendi MCP sürecinde üretiliyor, sunucuya hiç ulaşmıyor. Kapı
# oraya konunca (K1 ADIM 3) anahtarsız gelen her istek "onay iste" olurdu ve
# **Auto mod kart çıkarmaya başlardı** — kullanıcının açıkça istemediği şey:
# *"oto modda hiçbir sıkıntı yok zaten her şeyin otomatik çalışması gerek"*.
#
# Bu yüzden ikinci bir sinyal var: şu an KOŞAN bir turun modu. Anahtarlı yol
# (yukarısı) daha dar ve olduğu gibi duruyor; ortam turu yalnız anahtar
# YOKKEN sorulur.
#
# ⚠️ Dürüst sınır: bu, "bu çağrı gerçekten o turdan geldi" kanıtı DEĞİL. Auto
# bir tur koşarken ürüne bağlı başka bir MCP istemcisi (ör. Cursor) de o
# pencereden geçebilir. Kabul edilebilir olmasının sebebi ölçülmüş: bugün o
# istemcilerde kapı HİÇ YOK ve mutasyonlar sorgusuz geçiyor — yani bu, dar
# olmayan bir kapı değil, hiç olmayan bir kapının yerine gelen dar bir kapı.
# Turun BİTİŞİ sayaçla garanti: `with` bloğu istisna ve generator kapanışında
# da düşüyor, yani "auto turu bitti ama sinyal açık kaldı" hali oluşmuyor.

_AMBIENT_AUTO = 0
_AMBIENT_TOPLAM = 0


class ambient_turn:
    """Koşan turun modunu kaydeder; çıkışta MUTLAKA bırakır.

    Sayaç (bool değil) çünkü aynı anda birden fazla tur koşabiliyor: iç içe ya
    da paralel bir tur bittiğinde diğerininki hâlâ açık kalmalı. Bool olsaydı
    ilk biten, koşmaya devam eden turun sinyalini kapatırdı.

    İKİ sayaç tutuluyor, biri değil — sebebi aşağıda `ambient_auto_approve`'da.
    """

    def __init__(self, workspace_path: str, generation_mode: str) -> None:
        self._auto = generation_mode == "auto"

    def __enter__(self) -> "ambient_turn":
        global _AMBIENT_AUTO, _AMBIENT_TOPLAM
        with _LOCK:
            _AMBIENT_TOPLAM += 1
            if self._auto:
                _AMBIENT_AUTO += 1
        return self

    def __exit__(self, *_exc) -> None:
        global _AMBIENT_AUTO, _AMBIENT_TOPLAM
        with _LOCK:
            _AMBIENT_TOPLAM = max(0, _AMBIENT_TOPLAM - 1)
            if self._auto:
                _AMBIENT_AUTO = max(0, _AMBIENT_AUTO - 1)
        return None


def ambient_auto_approve() -> bool:
    """Koşan turların HEPSİ Auto modda mı?

    "En az biri" DEĞİL "hepsi" — ve fark bir açığı kapatıyor. İlk yazımı "en az
    bir auto turu var mı" idi; o hâliyle aynı anda bir auto ve bir step turu
    koşarken, STEP turunun mutasyonları da sessizce oto-onaylanırdı. Yani adım
    modunun kapısı, kullanıcının başka bir sekmede başlattığı ilgisiz bir auto
    turu yüzünden kaybolurdu — kapının varlık sebebini yok eden bir hal.

    Kapı ayrı süreçte olduğu için çağrının HANGİ turdan geldiğini bilemiyoruz;
    bilinemeyen bir şey hakkında en güvenli varsayım, koşanlardan herhangi biri
    onay istiyorsa onay istemektir. Bedeli: auto turu koşarken açılan bir step
    turu, auto turun kartlarını da geri getirir. Bu yön DOĞRU yön — fazladan
    kart bir rahatsızlık, eksik kart bir açık.
    """
    with _LOCK:
        return _AMBIENT_TOPLAM > 0 and _AMBIENT_AUTO == _AMBIENT_TOPLAM
