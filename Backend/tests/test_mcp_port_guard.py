"""8080 port temizliğinin regresyon testleri — 2026-07-27 denetim bulgusu.

Arıza: uygulama açılışta ve `stop_server`'da 8080'i LISTEN eden **her** PID'i
öldürüyordu. `-sTCP:LISTEN` filtresi yalnız "Unity Editor client bağlantısını
öldürme" hatasını kapatıyordu; kullanıcının alakasız bir dev server'ı hâlâ
sessizce ölüyordu.

Bu dosya kapının İKİ yönünü de sabitliyor. Tek yön sınansaydı hiçbir şeyi
öldürmeyen bir fonksiyon da testleri geçerdi — ve o zaman kendi yetim
sunucumuz portta kalır, uygulama bir daha hiç açılamazdı:

    yabancı süreç  → ÖLDÜRÜLMEZ, kullanıcıya sebep bildirilir
    kendi sürecimiz → ÖLDÜRÜLÜR

Gerçek süreç öldürülmüyor: `lsof`/`ps`/`os.kill` katmanı mock'lanıyor.
"""

import os

import pytest

from unity_ai_mcp import mcp_port_guard as guard
from unity_ai_mcp.mcp_port_guard import ProcessInfo

PORT = 8080

# Canlı ölçümden alınmış gerçek komut satırları (2026-07-27, macOS).
OUR_LISTENER_CMD = (
    "/opt/homebrew/.../Python /var/folders/.../archive-v0/XFCPZLc5n8IFgxJU/bin/"
    "mcp-for-unity --transport http --http-url http://127.0.0.1:8080 "
    "--project-scoped-tools"
)
OUR_UVX_CMD = (
    "/Users/x/.local/bin/uv tool uvx --no-cache --from /Users/x/unity-mcp/Server "
    "mcp-for-unity --transport http --http-url http://127.0.0.1:8080"
)
# Kullanıcının 8080'de duran alakasız dev server'ı — korunması gereken taraf.
FOREIGN_CMD = "node /Users/x/projects/blog/node_modules/.bin/next dev -p 8080"


@pytest.fixture
def fake_world(monkeypatch):
    """Süreç tablosunu ve öldürme çağrılarını taklit eder.

    `killed` listesi testin tek gözlem noktası: bir PID'in orada OLMAMASI
    "dokunulmadı"nın kanıtı.
    """

    class World:
        def __init__(self):
            self.listeners = []          # porta oturan PID'ler
            self.table = {}              # pid -> ProcessInfo
            self.killed = []

    world = World()

    monkeypatch.setattr(guard, "list_listening_pids", lambda port=PORT: list(world.listeners))
    monkeypatch.setattr(guard, "query_process", lambda pid: world.table.get(pid))

    def _fake_terminate(pid):
        world.killed.append(pid)
        return True

    monkeypatch.setattr(guard, "_terminate", _fake_terminate)
    return world


def _register(world, pid, command, ppid=1):
    world.table[pid] = ProcessInfo(pid=pid, ppid=ppid, command=command)


# ─── Yön 1: yabancı süreç ÖLDÜRÜLMEZ ────────────────────────────────────────


def test_foreign_process_is_not_killed(fake_world):
    _register(fake_world, 4242, FOREIGN_CMD)
    fake_world.listeners = [4242]

    result = guard.terminate_port_listeners(PORT)

    assert fake_world.killed == []            # asıl iddia: hiç öldürülmedi
    assert result.killed == []
    assert result.refused == [4242]


def test_foreign_process_produces_actionable_message(fake_world):
    """Sessiz başarısızlık kabul edilmiyor: kullanıcı ne yapacağını görmeli."""
    _register(fake_world, 4242, FOREIGN_CMD)
    fake_world.listeners = [4242]

    result = guard.terminate_port_listeners(PORT)

    assert "8080" in result.message
    assert "4242" in result.message


def test_foreign_process_survives_even_next_to_our_server(fake_world):
    """Karışık durum: aynı portu iki süreç raporlarsa yalnız bizimki ölmeli.

    Tek başına 'yabancı' testi, 'bir yabancı görünce hepsini bağışla' gibi
    yanlış bir düzeltmeyi yakalamaz.
    """
    _register(fake_world, 4242, FOREIGN_CMD)
    _register(fake_world, 5150, OUR_LISTENER_CMD)
    fake_world.listeners = [4242, 5150]

    result = guard.terminate_port_listeners(PORT)

    assert fake_world.killed == [5150]
    assert result.refused == [4242]


def test_unreadable_process_is_not_killed(fake_world):
    """Süreç tablosu okunamıyorsa (ps yok/izin yok) karar 'öldürme' olmalı.

    Doğrulanamayan bir süreci öldürmek, port çakışmasını çözememekten kötü.
    """
    fake_world.listeners = [9999]          # tabloda karşılığı YOK

    result = guard.terminate_port_listeners(PORT)

    assert fake_world.killed == []
    assert result.refused == [9999]


def test_foreign_owner_blocks_start_instead_of_killing(fake_world):
    """`foreign_port_owners` yalnız rapor eder — hiçbir şey öldürmez."""
    _register(fake_world, 4242, FOREIGN_CMD)
    fake_world.listeners = [4242]

    assert guard.foreign_port_owners(PORT) == [4242]
    assert fake_world.killed == []


# ─── Yön 2: kendi sürecimiz ÖLDÜRÜLÜR ───────────────────────────────────────


def test_our_server_is_killed_by_command_marker(fake_world):
    """Önceki oturumdan kalan yetim: ata zinciri yok, elde yalnız komut satırı."""
    _register(fake_world, 5150, OUR_LISTENER_CMD, ppid=1)
    fake_world.listeners = [5150]

    result = guard.terminate_port_listeners(PORT)

    assert fake_world.killed == [5150]
    assert result.killed == [5150]
    assert result.refused == []


def test_our_uvx_wrapper_is_also_recognized(fake_world):
    """Belirteç ara uvx sürecinin argv'sinde de var; port sahibi o olabilir."""
    _register(fake_world, 5133, OUR_UVX_CMD)
    fake_world.listeners = [5133]

    guard.terminate_port_listeners(PORT)

    assert fake_world.killed == [5133]


def test_descendant_is_killed_without_marker(fake_world):
    """Kendi ağacımızdaki torun, komut satırı tanınmasa da bizimdir.

    Gerçek yerleşimden: dinleyici bizim Popen çocuğumuz değil, uvx'in çocuğu.
    """
    me = os.getpid()
    _register(fake_world, 6001, "uvx wrapper", ppid=me)          # bizim çocuğumuz
    _register(fake_world, 6002, "some-renamed-binary", ppid=6001)  # torun = dinleyici
    fake_world.listeners = [6002]

    guard.terminate_port_listeners(PORT)

    assert fake_world.killed == [6002]


def test_explicitly_owned_pid_is_killed(fake_world):
    """Çağıran 'bunu ben başlattım' diyorsa bu en güçlü kanıt.

    Gerekiyor çünkü stop_server ata zincirini uvx ölmeden ÖNCE örnekliyor;
    öldürme anında torun çoktan init'e evlat edinilmiş olabilir.
    """
    _register(fake_world, 7007, "orphaned-after-reparent", ppid=1)
    fake_world.listeners = [7007]

    guard.terminate_port_listeners(PORT, owned_pids={7007})

    assert fake_world.killed == [7007]


def test_empty_port_is_a_no_op(fake_world):
    result = guard.terminate_port_listeners(PORT)
    assert result.killed == [] and result.refused == []
    assert fake_world.killed == []


def test_own_backend_pid_is_never_killed(fake_world):
    """Kendimizi öldürmeyelim — yanlış port yapılandırmasında felaket olurdu."""
    me = os.getpid()
    _register(fake_world, me, "python backend", ppid=1)
    fake_world.listeners = [me]

    guard.terminate_port_listeners(PORT)

    assert fake_world.killed == []


# ─── Çağıran taraf: main.py ve stop_server aynı kapıyı kullanıyor mu ─────────


def test_stop_server_does_not_kill_foreign_process(fake_world, monkeypatch):
    """stop_server, sunucumuz kapanmış ama port başkasındaysa dokunmamalı."""
    from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager

    _register(fake_world, 4242, FOREIGN_CMD)
    fake_world.listeners = [4242]
    monkeypatch.setattr(unity_mcp_manager, "process", None)
    monkeypatch.setattr(unity_mcp_manager, "is_running", lambda: True)

    unity_mcp_manager.stop_server()

    assert fake_world.killed == []


def test_stop_server_kills_our_own_server(fake_world, monkeypatch):
    from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager

    _register(fake_world, 5150, OUR_LISTENER_CMD)
    fake_world.listeners = [5150]

    class FakeProc:
        pid = 5133
        terminated = False

        def terminate(self):
            FakeProc.terminated = True

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(unity_mcp_manager, "process", FakeProc())
    monkeypatch.setattr(unity_mcp_manager, "is_running", lambda: False)

    unity_mcp_manager.stop_server()

    assert FakeProc.terminated is True          # kendi Popen çocuğumuz
    assert fake_world.killed == [5150]          # ve portu tutan torun


def test_start_server_refuses_when_port_is_foreign(fake_world, monkeypatch):
    """Yabancı süreç varken başlatma reddedilir ve sebep saklanır.

    Eski davranışta uvx sessizce bind edemiyor, start_server yine True dönüyor
    ve toggle sonsuza kadar sarıda kalıyordu.
    """
    from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager

    _register(fake_world, 4242, FOREIGN_CMD)
    fake_world.listeners = [4242]
    monkeypatch.setattr(unity_mcp_manager, "is_running", lambda: False)
    monkeypatch.setattr(unity_mcp_manager, "_starting", False)

    # Buraya kadar gelirse gerçek uvx spawn'ı olurdu — testin patlaması doğru.
    assert unity_mcp_manager.start_server() is False
    assert "8080" in (unity_mcp_manager.last_error or "")
    assert fake_world.killed == []


# ─── Ayrıştırıcılar (mock'suz, saf metin) ───────────────────────────────────


def test_lsof_output_parsing(monkeypatch):
    monkeypatch.setattr(guard.sys, "platform", "darwin")
    monkeypatch.setattr(guard, "_run", lambda cmd: "5150\n5133\n5150\n")
    assert guard.list_listening_pids(PORT) == [5150, 5133]


def test_missing_tool_yields_no_pids(monkeypatch):
    """`lsof` yoksa `_run` None döner; bunu 'port boş' saymak zararsız —
    hiçbir şey öldürülmez. Tersi (hata fırlatmak) açılışı kırardı."""
    monkeypatch.setattr(guard.sys, "platform", "darwin")
    monkeypatch.setattr(guard, "_run", lambda cmd: None)
    assert guard.list_listening_pids(PORT) == []


def test_netstat_parsing_ignores_similar_port(monkeypatch):
    """`:18080` yanlışlıkla `:8080` gibi eşleşmemeli (ayıraç dahil karşılaştırma)."""
    monkeypatch.setattr(guard.sys, "platform", "win32")
    monkeypatch.setattr(
        guard,
        "_run",
        lambda cmd: (
            "  TCP    0.0.0.0:18080          0.0.0.0:0    LISTENING       111\n"
            "  TCP    127.0.0.1:8080         0.0.0.0:0    LISTENING       222\n"
            "  TCP    127.0.0.1:8080         127.0.0.1:5  ESTABLISHED     333\n"
        ),
    )
    assert guard.list_listening_pids(PORT) == [222]
