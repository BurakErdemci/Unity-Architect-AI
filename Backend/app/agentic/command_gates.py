"""
Komut onay gate'leri — AgentRunner ve CLIProvider tarafından ortaklaşa kullanılır.
Circular import olmadan her iki modülün de import edebileceği paylaşılan store.
"""
import asyncio
from typing import Dict

# gate_id → asyncio.Event
APPROVAL_GATES: Dict[str, asyncio.Event] = {}
# gate_id → bool (True=onaylandı, False=reddedildi)
APPROVAL_RESULTS: Dict[str, bool] = {}

# AskUserQuestion (Claude SDK) için soru gate'leri — Opus kullanıcıya A/B/C soruyor,
# frontend seçimi /question-answer ile bildirir, can_use_tool callback'i burada bekler.
# gate_id → asyncio.Event
QUESTION_GATES: Dict[str, asyncio.Event] = {}
# gate_id → dict (soru metni → seçilen label(lar))
QUESTION_RESULTS: Dict[str, dict] = {}
