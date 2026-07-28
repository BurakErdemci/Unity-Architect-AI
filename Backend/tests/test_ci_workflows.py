"""CI workflow'larının SÖZLEŞMESİ: release yolu kalite kapısından geçmek zorunda.

Hangi arızadan doğdu (dış denetim, 2026-07-28): `test.yml` `tags-ignore: ['**']`
taşıyordu ve gerekçesi şu varsayıma dayanıyordu — *"tag her zaman daha önce push
edilmiş, yani zaten test görmüş bir commit'e atılır."* Varsayım YANLIŞ:

    git push origin <sha>:refs/tags/v1.0

hiçbir dala hiç girmemiş bir commit'i tag'ler. `release.yml` (`tags: ['v*']`) o
commit'i doğrudan paketleyip taslak release'e koyuyordu; hiçbir test koşmadan.
Yani kalite kapısı tam olarak en pahalı olduğu anda — kullanıcıya ikili gideceği
anda — devre dışıydı.

Bu testlerin ölçtüğü şey "workflow'lar geçerli YAML mi" değil (o yalnızca ön
koşul), **release üreten hiçbir job'ın kapıyı atlayamaması**. Beklentiler
dosyadan TÜRETİLMİYOR, buraya elle yazılıyor: bir testin beklentisini ölçtüğü
şeyden üretmesi bu depoda ölçülmüş bir tuzak (eşitliğin iki tarafı da aynı
sabitten gelirse test hiçbir zaman kırmızı olamaz).
"""
import os

import pytest

yaml = pytest.importorskip("yaml", reason="PyYAML yoksa workflow sözleşmesi ölçülemez")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_WF_DIR = os.path.join(_ROOT, ".github", "workflows")

# Reusable workflow çağrısında GitHub'ın beklediği tam gösterim. Elle yazılı:
# `test.yml`'den okunsaydı test kendi beklentisini ölçtüğü şeyden üretirdi.
_TEST_WF_REF = "./.github/workflows/test.yml"


def _yukle(ad: str) -> dict:
    path = os.path.join(_WF_DIR, ad)
    assert os.path.isfile(path), f"beklenen workflow yok: {path}"
    with open(path, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    assert isinstance(doc, dict), f"{ad} bir eşleme değil"
    return doc


def _triggers(doc: dict) -> dict:
    """`on:` bloğu. YAML 1.1'de `on` bir BOOLEAN'dır ve PyYAML onu `True`
    anahtarına çevirir — bu tuzağa düşen bir test, bloğu hiç bulamadığı için
    sessizce hiçbir şey ölçmezdi."""
    for anahtar in ("on", True):
        if anahtar in doc:
            blok = doc[anahtar]
            assert isinstance(blok, dict), "on: bloğu eşleme değil"
            return blok
    pytest.fail("workflow'da `on:` bloğu yok")


def _jobs(doc: dict) -> dict:
    jobs = doc.get("jobs")
    assert isinstance(jobs, dict) and jobs, "workflow'da job yok"
    return jobs


def _needs(job: dict) -> set:
    n = job.get("needs")
    if n is None:
        return set()
    return {n} if isinstance(n, str) else set(n)


def _kapali_bagimliliklar(jobs: dict, job_adi: str) -> set:
    """`needs` grafiğinin geçişli kapanışı. Doğrudan `needs`e bakmak yetmez:
    araya bir job eklenip zincir koparıldığında test yine yeşil kalırdı."""
    goruldu, yigin = set(), [job_adi]
    while yigin:
        for bagimli in _needs(jobs.get(yigin.pop(), {})):
            if bagimli not in goruldu:
                goruldu.add(bagimli)
                yigin.append(bagimli)
    return goruldu


@pytest.fixture(scope="module")
def test_wf():
    return _yukle("test.yml")


@pytest.fixture(scope="module")
def release_wf():
    return _yukle("release.yml")


class TestWorkflowlarAyristirilabilir:
    """Ön koşul. Bozuk bir YAML GitHub'da ancak tag atıldıktan SONRA görünür ve
    o noktada kapı zaten kaybolmuştur."""

    @pytest.mark.parametrize("ad", ["test.yml", "release.yml"])
    def test_the_workflow_parses_and_has_jobs(self, ad):
        _jobs(_yukle(ad))


class TestReleaseYoluKapiyiAtlayamiyor:
    """Asıl bulgu. Ölçülen şey `test.yml`'in var olması değil, release üreten
    job'ların ONA BAĞLI olması."""

    def test_release_still_triggers_on_v_tags(self, release_wf):
        """Kontrol: düzeltme release'in tetikleyicisini bozmamalı."""
        tags = _triggers(release_wf)["push"]["tags"]
        assert "v*" in tags, f"release artık v* tag'inde koşmuyor: {tags}"

    def test_test_workflow_is_callable(self, test_wf):
        """`workflow_call` olmadan `release.yml` onu `uses:` ile çağıramaz —
        ve çağrı sessizce başarısız olmaz, workflow HİÇ koşmaz."""
        assert "workflow_call" in _triggers(test_wf), (
            "test.yml `workflow_call` ile çağrılabilir değil"
        )

    def test_a_release_job_calls_the_test_workflow(self, release_wf):
        cagiranlar = [ad for ad, j in _jobs(release_wf).items()
                      if j.get("uses") == _TEST_WF_REF]
        assert cagiranlar, (
            f"release.yml hiçbir job'ta {_TEST_WF_REF} çağırmıyor — kalite kapısı "
            "release yolunda yok"
        )

    @pytest.mark.parametrize("job_adi", ["build", "release"])
    def test_every_artifact_producing_job_depends_on_the_gate(self, release_wf, job_adi):
        """İki yönün 'ateşlenmesi gereken' tarafı: ikili üreten ve release yayan
        job'ların İKİSİ de kapının ardında olmalı. `release` job'ının `build`e
        bağlı olması yetmez — o zincir de burada, geçişli olarak ölçülüyor."""
        jobs = _jobs(release_wf)
        assert job_adi in jobs, f"release.yml'de '{job_adi}' job'ı yok"
        kapi = {ad for ad, j in jobs.items() if j.get("uses") == _TEST_WF_REF}
        bagimliliklar = _kapali_bagimliliklar(jobs, job_adi)
        assert kapi & bagimliliklar, (
            f"'{job_adi}' kalite kapısına bağlı değil (needs kapanışı: "
            f"{sorted(bagimliliklar) or 'boş'}) — kapı yeşil yanmadan koşabilir"
        )

    def test_the_gate_job_itself_waits_for_nothing_in_release(self, release_wf):
        """Karşı yön: kapı job'ı build'e bağlanırsa kapı olmaktan çıkar, build
        SONRASI bir rapora dönüşür (ve `needs` döngüsü workflow'u geçersiz kılar)."""
        jobs = _jobs(release_wf)
        for ad, j in jobs.items():
            if j.get("uses") == _TEST_WF_REF:
                assert not _needs(j), (
                    f"kapı job'ı '{ad}' başka job'ları bekliyor: {_needs(j)}"
                )


class TestCiftKosuHalaOnleniyor:
    """Düzeltmenin bedeli ölçülüyor: tag push'unda `test.yml` AYRICA kendi
    başına koşmamalı. Koşarsa aynı commit için iki tam test koşusu olur ve
    release build'iyle runner kuyruğu paylaşılır — `tags-ignore`ı yazdıran
    kaygı buydu ve hâlâ geçerli."""

    def test_test_workflow_is_not_triggered_by_tag_push_itself(self, test_wf):
        push = _triggers(test_wf)["push"]
        assert "tags" not in push, (
            "test.yml tag push'unda da doğrudan koşuyor — release.yml onu zaten "
            "çağırdığı için bu ikinci bir tam koşu demek"
        )
        assert push.get("tags-ignore"), "tag'ler dışlanmamış"

    def test_ordinary_branch_and_pr_pushes_are_still_gated(self, test_wf):
        """Karşı yön: `workflow_call` eklenirken normal tetikleyiciler
        düşmemeli, yoksa günlük geliştirmede kapı hiç ateşlenmez."""
        tetik = _triggers(test_wf)
        assert "**" in tetik["push"]["branches"], "dal push'ları artık test edilmiyor"
        assert "pull_request" in tetik, "PR'lar artık test edilmiyor"


class TestKapiGercektenIsKosuyor:
    """`test.yml` bir kabuk olsaydı (job'ı boşaltılsa) yukarıdaki bağların hepsi
    yeşil kalırdı. Kapının ARKASINDA gerçekten pytest ve vitest olmalı."""

    def test_the_gate_runs_both_backend_and_frontend_suites(self, test_wf):
        komutlar = " ".join(
            str(adim.get("run", ""))
            for job in _jobs(test_wf).values()
            for adim in (job.get("steps") or [])
        )
        for beklenen in ("pytest", "vitest", "tsc"):
            assert beklenen in komutlar, f"kalite kapısında '{beklenen}' koşmuyor"
