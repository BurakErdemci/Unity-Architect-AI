"""
Komut onay gate'leri — AgentRunner ve CLIProvider tarafından ortaklaşa kullanılır.
Circular import olmadan her iki modülün de import edebileceği paylaşılan store.
"""
import asyncio
from typing import Dict

# Onay kapısının kullanıcı cevabını bekleme süresi — TEK KAYNAK.
# Ölçüldü (2026-07-28): `agent_runner` üç ayrı yerde 60.0 ile beklerken
# `claude_sdk_session` ve `codex_session` 300.0 ile bekliyordu. 60 sn dolunca
# backend `approved=False` yapıp gate'i siliyordu → 90. saniyede "Onayla" diyen
# kullanıcının onayı SESSİZCE reddedilmiş oluyordu (hata yok, kart kaybolmuyor).
# Arızanın şekli "uyuşması gereken N yer", o yüzden literal tekrar EDİLMEZ.
# Evi burası: gate store'unu zaten hem AgentRunner hem sağlayıcılar buradan
# alıyor ve bu modül circular-import'suz olacak şekilde tasarlandı — sabiti
# `agent_runner`'da tutmak sağlayıcıdan agentic'e yeni bir import yönü açıyordu.
APPROVAL_TIMEOUT_S = 300.0

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
