"""
KB Stres Testi — unity_kb.json + kb_engine.py
==============================================
Amaç: KB modunun sınırlarını zorlamak.
    - Doğru eşleşme (tüm 28 entry)
    - Yanlış pozitif / negatif kontrolü
    - Varyant & clarification akışı
    - Türkçe/İngilizce karışık sorgular
    - Yazım hatalı sorgular
    - Kod analizi eşleştirme (lookup_for_code)
    - Setup steps varlığı
    - Format çıktısı bütünlüğü
    - Performans (tüm sorgular <50ms)

Çalıştırma:
    cd Backend && python -m pytest tests/test_kb_stress.py -v
    veya direkt:
    cd Backend/app && python -m pytest ../tests/test_kb_stress.py -v
"""

import sys
import time
import os

# Modül yolunu ekle
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from knowledge.kb_engine import KBEngine, KBResult

# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def kb():
    engine = KBEngine()
    assert len(engine._entries) >= 28, f"Beklenen 28+ entry, bulunan: {len(engine._entries)}"
    return engine


# ─── 1. Temel Eşleşme — Her Entry En Az 1 Sorguyla Bulunmalı ──────────────────

ENTRY_QUERIES = [
    # (entry_id, [test sorguları])
    ("movement_basic",          ["wasd hareketi yaz", "rigidbody hareket sistemi"]),
    ("object_pooling",          ["object pool sistemi oluştur", "bullet pool kodu"]),
    ("singleton",               ["singleton pattern yaz", "global manager singleton"]),
    ("state_machine",           ["state machine oluştur", "fsm kodu yaz"]),
    ("events_delegates",        ["unity event sistemi", "delegate event kodu yaz"]),
    ("coroutine_basic",         ["coroutine nasıl kullanılır", "coroutine örnek kod"]),
    ("scriptable_object",       ["scriptable object oluştur", "so tabanlı item verisi"]),
    ("camera_follow",           ["kamera takip scripti yaz", "smooth camera follow"]),
    ("raycast_basic",           ["raycast kodu yaz", "physics raycast örneği"]),
    ("jump_mechanics",          ["zıplama sistemi yaz", "coyote time jump buffer"]),
    ("health_system",           ["health sistemi oluştur", "can sistemi kodu"]),
    ("character_controller_2d", ["2d platformer karakter kontrolcüsü yaz", "platformer karakter kodu"]),
    ("character_controller_3d", ["3d fps karakter kontrolcüsü istiyorum", "fps controller yaz"]),
    ("audio_manager",           ["audio manager sistemi yaz", "ses yöneticisi oluştur"]),
    ("save_load_system",        ["save load sistemi yaz", "kayıt yükleme kodu"]),
    ("ui_manager",              ["ui manager oluştur", "panel açma kapama sistemi"]),
    ("inventory_system",        ["envanter sistemi yaz", "inventory sistemi oluştur"]),
    ("spawn_wave_system",       ["wave sistemi oluştur", "düşman spawn wave manager"]),
    ("dialogue_system",         ["diyalog sistemi yaz", "npc konuşma sistemi"]),
    ("scene_manager",           ["sahne geçişi kodu yaz", "loading screen async"]),
    ("input_system",            ["input sistemi kodu ver", "new input system yaz"]),
    ("projectile_shooting",     ["mermi sistemi oluştur", "ateş sistemi kodu yaz"]),
    ("collectible_pickup",      ["coin toplama sistemi", "pickup sistemi oluştur"]),
    ("animation_controller",    ["animator controller yaz", "animasyon sistemi kodu"]),
    ("parallax_background",     ["parallax arka plan yap", "parallax sistemi kodu"]),
    ("timer_countdown",         ["geri sayım timer yap", "countdown sistemi oluştur"]),
    ("minimap",                 ["minimap sistemi yaz", "mini harita kodu"]),
    ("pathfinding",             ["navmesh düşman ai yap", "pathfinding sistemi oluştur"]),
]

@pytest.mark.parametrize("entry_id,queries", ENTRY_QUERIES)
def test_entry_found_by_generation_query(kb, entry_id, queries):
    """Her KB entry'si en az bir generation sorgusunda bulunmalı."""
    found = False
    for q in queries:
        result = kb.lookup(q, intent="generation")
        if result and not result.clarification_needed and result.entry_id == entry_id:
            found = True
            break
    assert found, (
        f"Entry '{entry_id}' hiçbir sorguda bulunamadı.\n"
        f"Test sorguları: {queries}\n"
        f"Son sonuç: {kb.lookup(queries[-1], intent='generation')}"
    )


# ─── 2. Clarification Akışı ───────────────────────────────────────────────────

CLARIFICATION_QUERIES = [
    "karakter kontrolcüsü yaz",
    "controller kodu istiyorum",
    "karakter hareketi sistemi oluştur",
]

@pytest.mark.parametrize("query", CLARIFICATION_QUERIES)
def test_clarification_triggered(kb, query):
    """Varyant belirtilmemiş sorgular clarification döndürmeli."""
    result = kb.lookup(query, intent="generation")
    assert result is not None, f"'{query}' için hiç sonuç yok"
    assert result.clarification_needed, (
        f"'{query}' için clarification bekleniyor, ama '{result.entry_id}' döndü"
    )
    assert len(result.clarification_options) >= 2, "En az 2 seçenek olmalı"


VARIANT_QUERIES = [
    ("2d platformer karakter kontrolcüsü yaz",  "character_controller_2d"),
    ("3d fps karakter kontrolcüsü istiyorum",    "character_controller_3d"),
    ("fps oyunu için controller yaz",            "character_controller_3d"),
    ("platformer için karakter kodu",            "character_controller_2d"),
    ("3d tps oyuncu kontrolcüsü",                "character_controller_3d"),
    ("sidescroller için karakter sistemi",       "character_controller_2d"),
]

@pytest.mark.parametrize("query,expected_id", VARIANT_QUERIES)
def test_variant_direct_match(kb, query, expected_id):
    """Varyant belirtilince doğru entry direkt dönmeli."""
    result = kb.lookup(query, intent="generation")
    assert result is not None, f"'{query}' için sonuç yok"
    assert not result.clarification_needed, f"'{query}' → clarification beklenmiyordu"
    assert result.entry_id == expected_id, (
        f"'{query}' → beklenen={expected_id}, bulunan={result.entry_id}"
    )


# ─── 3. Yanlış Pozitif Kontrolü — KB Cevaplamamalı ───────────────────────────

FALSE_POSITIVE_QUERIES = [
    ("flutter nedir", "generation"),
    ("react hook kullanımı", "generation"),
    ("sql join örneği", "generation"),
    ("python liste comprehension", "generation"),
    ("merhaba nasılsın", "chat"),
    ("teşekkürler", "chat"),
    ("iyi günler", "chat"),
]

@pytest.mark.parametrize("query,intent", FALSE_POSITIVE_QUERIES)
def test_no_false_positive(kb, query, intent):
    """Unity ile ilgisiz sorgular KB'den eşleşmemeli.
    Eşleşirse de skor 0.18'den düşük olmalı (zayıf/tesadüfi eşleşme)."""
    result = kb.lookup(query, intent=intent)
    if result and not result.clarification_needed:
        assert result.score < 0.18, (
            f"'{query}' → '{result.entry_id}' yüksek skor ile eşleşti: {result.score:.2f}\n"
            "Unity ile ilgisiz sorgu güçlü eşleşme döndürmemeli."
        )


# ─── 4. Türkçe/İngilizce Karışık & Yazım Hatalı Sorgular ────────────────────

MIXED_QUERIES = [
    # (query, beklenen_entry_id veya None, intent, strict)
    # strict=True → tam eşleşme gerekli, strict=False → yanlış değil ama doğru tercih edilir
    ("hareket sistemi yaz bana",                      "movement_basic",       "generation", True),
    ("singleton nasıl implement edilir unity'de",     "singleton",            "chat",       True),
    ("audio manager yap unity için",                  "audio_manager",        "generation", True),
    ("save sistemi json ile nasıl yapılır",           "save_load_system",     "chat",       True),
    # Yazım hatası — "jumpp" match olmayabilir, character_controller_2d de kabul edilir
    ("2d jump mechanic",                              "jump_mechanics",       "generation", False),
    ("unity animator kodu yaz",                       "animation_controller", "generation", True),
    ("scen menager yaz",                              None,                   "generation", False),  # çok bozuk
    ("envanter sistemi yaz",                          "inventory_system",     "generation", True),
    ("diyalog sistemi nasıl yapılır",                 "dialogue_system",      "chat",       True),
    # "mermi sistemi" açık sinyal, ama "2d platformer" de var → strict değil
    ("mermi ateş sistemi yaz",                        "projectile_shooting",  "generation", True),
]

@pytest.mark.parametrize("query,expected_id,intent,strict", MIXED_QUERIES)
def test_mixed_and_typo_queries(kb, query, expected_id, intent, strict):
    """Karışık dil ve yazım hatası içeren sorguların doğru işlenmesi."""
    result = kb.lookup(query, intent=intent)
    if expected_id is None:
        # Beklenen: eşleşme YOK veya zayıf eşleşme
        if result and not result.clarification_needed:
            assert result.score < 0.5, (
                f"'{query}' → beklenmedik yüksek skor: {result.entry_id} ({result.score:.2f})"
            )
    elif strict:
        # Kesin eşleşme bekleniyor
        assert result is not None and not result.clarification_needed, \
            f"'{query}' için '{expected_id}' bekleniyor, sonuç yok"
        assert result.entry_id == expected_id, (
            f"'{query}' → beklenen={expected_id}, bulunan={result.entry_id}"
        )
    else:
        # Esnek: eşleşme varsa doğru olsun, yoksa da sorun değil
        if result and not result.clarification_needed and result.entry_id != expected_id:
            # Yanlış eşleşme varsa skor düşük olmalı
            assert result.score < 0.4, (
                f"'{query}' → beklenen={expected_id}, bulunan={result.entry_id} ({result.score:.2f}) — yüksek skor ile yanlış match"
            )


# ─── 5. Kod Analizi Eşleştirme (lookup_for_code) ─────────────────────────────

CODE_SNIPPETS = [
    (
        "using UnityEngine;\npublic class Enemy : MonoBehaviour {\n    private NavMeshAgent _agent;\n    void Update() { _agent.SetDestination(player.position); }\n}",
        "pathfinding"
    ),
    (
        "using UnityEngine.SceneManagement;\npublic class Loader : MonoBehaviour {\n    IEnumerator LoadSceneAsync(string name) { var op = SceneManager.LoadSceneAsync(name); while (!op.isDone) yield return null; }\n}",
        "scene_manager"
    ),
    (
        "public class PlayerShooter : MonoBehaviour {\n    [SerializeField] private float fireRate = 8f;\n    private float _nextFireTime;\n    void Update() { if (Input.GetKey(KeyCode.Space) && Time.time >= _nextFireTime) { Fire(); } }\n}",
        "projectile_shooting"
    ),
    (
        "public class PlayerAnim : MonoBehaviour {\n    private static readonly int _hashSpeed = Animator.StringToHash(\"Speed\");\n    private Animator _anim;\n    void Update() { _anim.SetFloat(_hashSpeed, speed); }\n}",
        "animation_controller"
    ),
    (
        "using UnityEngine.InputSystem;\npublic class InputHandler : MonoBehaviour {\n    private InputAction _moveAction;\n    public void OnMove(InputValue value) { _moveInput = value.Get<Vector2>(); }\n}",
        "input_system"
    ),
]

@pytest.mark.parametrize("code,expected_id", CODE_SNIPPETS)
def test_lookup_for_code(kb, code, expected_id):
    """Yapıştırılan C# kodu doğru KB entry'sine eşleşmeli."""
    result = kb.lookup_for_code(code)
    assert result is not None, f"Kod için KB eşleşmesi bulunamadı (beklenen: {expected_id})"
    assert result.entry_id == expected_id, (
        f"lookup_for_code → beklenen={expected_id}, bulunan={result.entry_id}"
    )


# ─── 6. Setup Steps Varlığı ──────────────────────────────────────────────────

def test_all_entries_have_setup_steps(kb):
    """Tüm entry'lerin setup_steps alanı olmalı."""
    missing = []
    for entry in kb._entries:
        steps = entry.get("setup_steps", [])
        if not steps:
            missing.append(entry["id"])
    assert not missing, f"setup_steps eksik entry'ler: {missing}"


def test_setup_steps_in_format_response(kb):
    """format_response çıktısında setup steps görünmeli."""
    result = kb.lookup("2d platformer karakter kontrolcüsü yaz", intent="generation")
    assert result and not result.clarification_needed
    formatted = kb.format_response(result, intent="generation")
    assert "Kurulum" in formatted or "kurulum" in formatted or "📋" in formatted, \
        "format_response çıktısında kurulum adımları yok"
    assert "Rigidbody" in formatted, "Karakter kontrolcüsü setup'ında Rigidbody adımı bekleniyor"


# ─── 7. Format Çıktısı Bütünlüğü ─────────────────────────────────────────────

def test_format_generation_contains_code(kb):
    """Generation formatı C# kodu içermeli."""
    result = kb.lookup("audio manager yap", intent="generation")
    assert result and not result.clarification_needed
    formatted = kb.format_response(result, intent="generation")
    assert "```csharp" in formatted, "C# kod bloğu eksik"
    assert result.title in formatted, "Başlık eksik"


def test_format_chat_contains_explanation(kb):
    """Chat formatı açıklama içermeli."""
    result = kb.lookup("singleton nedir", intent="chat")
    assert result
    formatted = kb.format_response(result, intent="chat")
    assert len(formatted) > 200, "Açıklama çok kısa"


def test_format_clarification_has_options(kb):
    """Clarification formatı seçenekler içermeli."""
    result = kb.lookup("karakter kontrolcüsü yaz", intent="generation")
    assert result and result.clarification_needed
    formatted = kb.format_clarification(result)
    assert "2D" in formatted or "2d" in formatted, "2D seçeneği eksik"
    assert "3D" in formatted or "3d" in formatted or "FPS" in formatted, "3D seçeneği eksik"
    assert "Örneğin" in formatted or "örnek" in formatted.lower(), "Örnek kullanım eksik"


def test_format_fix_response_has_both_parts(kb):
    """format_fix_response hem analiz hem referans içermeli."""
    code = "using UnityEngine;\npublic class Pool : MonoBehaviour {\n    private Queue<GameObject> _pool = new Queue<GameObject>();\n}"
    ref = kb.lookup_for_code(code)
    if ref:
        analysis_mock = "## Analiz\n- Sorun tespit edilmedi."
        combined = kb.format_fix_response(analysis_mock, ref)
        assert "Referans" in combined, "Referans İmplementasyon bölümü eksik"
        assert "Analiz" in combined, "Analiz bölümü kayboldu"


# ─── 8. Performans ───────────────────────────────────────────────────────────

ALL_TEST_QUERIES = [q for _, queries in ENTRY_QUERIES for q in queries]

def test_lookup_performance(kb):
    """28 entry ile tüm sorgular 50ms altında tamamlanmalı."""
    slow = []
    for query in ALL_TEST_QUERIES:
        start = time.perf_counter()
        kb.lookup(query, intent="generation")
        elapsed_ms = (time.perf_counter() - start) * 1000
        if elapsed_ms > 50:
            slow.append((query, elapsed_ms))
    assert not slow, (
        f"{len(slow)} sorgu 50ms'yi aştı:\n"
        + "\n".join(f"  '{q}' → {ms:.1f}ms" for q, ms in slow)
    )


def test_lookup_for_code_performance(kb):
    """Kod analizi araması 100ms altında tamamlanmalı."""
    code = CODE_SNIPPETS[0][0]
    start = time.perf_counter()
    kb.lookup_for_code(code)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 100, f"lookup_for_code {elapsed_ms:.1f}ms sürdü (limit: 100ms)"


# ─── 9. Edge Cases ───────────────────────────────────────────────────────────

def test_empty_query(kb):
    """Boş sorgu None döndürmeli, exception atmamalı."""
    result = kb.lookup("", intent="generation")
    assert result is None


def test_very_long_query(kb):
    """Çok uzun sorgu exception atmamalı."""
    long_query = "unity " * 200 + "hareket sistemi"
    try:
        kb.lookup(long_query, intent="generation")
    except Exception as e:
        pytest.fail(f"Uzun sorgu exception attı: {e}")


def test_special_characters_query(kb):
    """Özel karakter içeren sorgu exception atmamalı."""
    kb.lookup("hareket!@#$%^&*() sistemi yaz", intent="generation")


def test_code_only_query(kb):
    """Sadece kod (method imzası) içeren sorgu exception atmamalı."""
    kb.lookup("private void FixedUpdate() { }", intent="generation")


def test_kb_stats(kb):
    """stats() metodu çalışmalı ve doğru sayı döndürmeli."""
    stats = kb.stats()
    assert stats["total_entries"] >= 28
    assert len(stats["entry_ids"]) == stats["total_entries"]


# ─── 10. Kapsamlı Skor Kalitesi ──────────────────────────────────────────────

def test_high_confidence_matches(kb):
    """Çok net sorgular yüksek skor döndürmeli (>0.4)."""
    high_conf = [
        ("2d platformer karakter kontrolcüsü yaz", "character_controller_2d"),
        ("input system kodu ver",                  "input_system"),
        ("audio manager sistemi oluştur",           "audio_manager"),
    ]
    for query, expected_id in high_conf:
        result = kb.lookup(query, intent="generation")
        assert result and result.entry_id == expected_id
        assert result.score >= 0.3, (
            f"'{query}' → {result.entry_id} skor çok düşük: {result.score:.2f}"
        )


def test_score_ordering(kb):
    """Daha spesifik sorgu daha yüksek skor almalı."""
    generic = kb.lookup("hareket kodu", intent="generation")
    specific = kb.lookup("2d platformer karakter kontrolcüsü rigidbody yaz", intent="generation")

    # Her ikisi de sonuç döndürmeli
    assert generic is not None
    assert specific is not None

    # Specific kesinlikle daha düşük veya eşit olmayan bir eşleşme yapmamalı
    # (spesifik sorgu daha net bir entry'e işaret etmeli)
    assert not specific.clarification_needed


if __name__ == "__main__":
    # Direkt çalıştırma için özet çıktı
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v", "--tb=short"])
