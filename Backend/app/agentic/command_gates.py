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
