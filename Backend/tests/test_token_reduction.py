"""Token-şişme düzeltmelerinin (Fix 1 prompt relax + Fix 3 transcript trim) yapısal
doğrulaması. Fix 2 (Anthropic caching) canlı çağrıda usage.cache_read_input_tokens ile
görülür; burada byte-identik system prefix ve compile ile dolaylı doğrulanır."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


class TestFix1PromptRelax(unittest.TestCase):
    def test_forced_scan_mandate_removed(self):
        from prompts import SYSTEM_PROMPT
        # Eski "her cevaptan önce MUTLAKA hierarchy çağır" dayatması kaldırıldı
        self.assertNotIn("MCP — ZORUNLU", SYSTEM_PROMPT)
        self.assertNotIn("Çağırmadan cevap verme", SYSTEM_PROMPT)
        # Yeni koşullu (talep-güdümlü) ifade var
        self.assertIn("MCP — GEREKTİĞİNDE", SYSTEM_PROMPT)

    def test_no_hallucination_guarantee_kept(self):
        from prompts import SYSTEM_PROMPT
        # "Asla uydurma" güvencesi KORUNDU (Fix 1 bunu bozmamalı)
        self.assertIn("ASLA TAHMİN ETME", SYSTEM_PROMPT)
        self.assertIn("uydurma", SYSTEM_PROMPT)


class TestFix3TranscriptTrim(unittest.TestCase):
    def test_budget_bounded(self):
        from routes.conversation_routes import _build_handoff_context
        msgs = [{"role": "user" if i % 2 == 0 else "assistant",
                 "content": "X" * 10000} for i in range(50)]
        msgs.append({"role": "user", "content": "son mesaj (hariç tutulur)"})
        out = _build_handoff_context("", msgs)
        # Eski tavan 40k+ idi; yeni 20k bütçe ile belirgin altında olmalı
        self.assertGreater(len(out), 0)
        self.assertLess(len(out), 30000)

    def test_recent_preserved_oldest_dropped(self):
        from routes.conversation_routes import _build_handoff_context
        msgs = [{"role": "user", "content": f"MSG{i} " + "y" * 3000} for i in range(30)]
        msgs.append({"role": "user", "content": "current"})
        out = _build_handoff_context("", msgs)
        self.assertIn("MSG28", out)      # en yeni (son hariç) korunur
        self.assertNotIn("MSG0 ", out)   # en eski bütçeden düşer


if __name__ == "__main__":
    unittest.main()
