"""Onay kapısı araç seçimine göre değişmemeli — 2026-07-27 E grubu bulgusu.

Ölçülen asimetri: `rm dosya` onay kartı çıkarıyordu, aynı dosyayı silen
`delete_file` çıkarmıyordu. Model kapıyı geçmek yerine kapısı olmayan aracı
seçebiliyordu; iki yol da aynı geri alınamaz etkiyi üretiyor.
"""

import pytest

from agentic.agent_runner import AgentRunner


@pytest.fixture
def runner(tmp_path):
    """Sağlayıcı kurmadan yalnız sınıflandırma davranışını sınıyoruz."""
    r = AgentRunner.__new__(AgentRunner)
    r.workspace_path = str(tmp_path)
    return r


def test_delete_file_requires_approval(runner):
    prompt = runner._approval_prompt("delete_file", {"file_path": "Assets/X.cs"})
    assert prompt and "Assets/X.cs" in prompt


def test_rm_and_delete_file_are_symmetric(runner):
    """Asıl bulgu: aynı etki, iki farklı kapı."""
    assert runner._approval_prompt("run_command", {"command": "rm Assets/X.cs"})
    assert runner._approval_prompt("delete_file", {"file_path": "Assets/X.cs"})


def test_write_file_stays_ungated(runner):
    """Bilerek: her yazımda onay istemek kullanıcıyı refleks-onaya alıştırır.
    Bu yön olmadan 'her aracı kapıya sok' değişikliği testlerden geçerdi."""
    assert runner._approval_prompt("write_file", {"file_path": "Assets/X.cs", "content": "x"}) is None
    assert runner._approval_prompt("read_file", {"file_path": "Assets/X.cs"}) is None


def test_safe_command_still_ungated(runner):
    assert runner._approval_prompt("run_command", {"command": "ls"}) is None
