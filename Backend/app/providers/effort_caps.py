"""Effort/reasoning yetenek kayıtçısı — TEK KAYNAK.

Her provider+model için: hangi seviyeler GERÇEKTEN destekleniyor (UI bunu gösterir)
ve seçilen seviye hangi ham parametreye çevrilir (dallar bunu uygular).
Araştırma matrisi: docs/superpowers/plans/2026-07-16-effort-redesign.md (kaynaklı).

Kanonik seviye skalası (UI sırası): auto < off < minimal < low < medium < high < xhigh < max
- "auto": HİÇBİR parametre gönderilmez → model kendi varsayılanıyla çalışır.
- "off": düşünme kapatılır (yalnız destekleyen modellerde listelenir).
map_effort(...) SÖZLEŞMESİ — dönen dict anahtarları (hepsi opsiyonel, auto → {}):
  request_params: OpenAI-uyumlu chat.completions.create'e üst-seviye eklenecekler
  extra_body:     OpenAI SDK extra_body içeriği (NIM chat_template_kwargs, z-ai thinking…)
  anthropic_extra_body: Anthropic SDK extra_body (output_config.effort — SDK sürümünden bağımsız)
  gemini_thinking_level / gemini_thinking_budget: google-generativeai ThinkingConfig için
      (İKİSİ BİRDEN ASLA — gemini-3.x'te birlikte göndermek 400 döner)
  cli_config:     Codex launch config'i ({"model_reasoning_effort": "..."})
  cli_flags:      argv'ye eklenecek bayraklar (copilot ["--effort", lvl])
  sdk_effort:     Claude Agent SDK options.effort değeri
"""
from __future__ import annotations

CANON_ORDER = ["auto", "off", "minimal", "low", "medium", "high", "xhigh", "max"]


def _caps(levels: list[str], note: str = "") -> dict:
    return {"levels": levels, "default": "auto", "note": note}


def get_effort_caps(provider_type: str, model_name: str) -> dict:
    """UI'nin göstereceği seviye listesi. 'auto' HER ZAMAN ilk seçenek."""
    p = (provider_type or "").lower()
    m = (model_name or "").lower()

    if p == "subscription":
        if m.startswith("claude-"):
            if "haiku" in m:
                return _caps(["auto"], "Haiku effort desteklemez — model varsayılanıyla çalışır.")
            if "4-6" in m or "4.6" in m:
                return _caps(["auto", "low", "medium", "high", "max"], "Bu modelde xhigh yok.")
            return _caps(["auto", "low", "medium", "high", "xhigh", "max"])
        if m.startswith("gpt-"):
            base = ["auto", "minimal", "low", "medium", "high", "xhigh"]
            if m.startswith("gpt-5.6"):
                return _caps(base + ["max"], "max: GPT-5.6 ailesine özel en derin tek-görev düşünme.")
            return _caps(base)
        if m.startswith("copilot-"):
            if m == "copilot-auto":
                # Canlı doğrulanmış: 'Model "auto" does not support reasoning effort'
                return _caps(["auto"], "Copilot Auto modeli effort kabul etmez.")
            # v1.0.60+ --effort; max yalnız Anthropic modellerde
            base = ["auto", "off", "minimal", "low", "medium", "high"]
            if "claude" in m or "sonnet" in m or "opus" in m or "haiku" in m:
                return _caps(base + ["max"])
            return _caps(base)
        if m.startswith("opencode:"):
            return _caps(["auto", "low", "medium", "high"],
                         "opencode.json model seçeneğiyle uygulanır (bir sonraki turda etkin).")
        if m.startswith("cursor-"):
            return _caps(["auto"], "Cursor CLI reasoning seçimi upstream bug nedeniyle çalışmıyor.")
        if m.startswith("kimi-"):
            return _caps(["auto"], "Kimi K3 düşünmesi her zaman açık — ayrı effort seviyesi yok.")
        # gemini/agy-*: agy CLI effort knob'u sunmuyor (model seçimiyle)
        return _caps(["auto"], "Antigravity effort'u model seçimine gömer — ayrı seviye sunmaz.")

    if p == "google":
        if "gemini-3" in m:
            levels = ["auto", "low", "high"] if ("3-pro" in m) else ["auto", "minimal", "low", "medium", "high"]
            return _caps(levels)
        return _caps(["auto", "off", "low", "medium", "high"], "Gemini 2.5: düşünme bütçesi (token) ile.")

    if p == "anthropic":
        if "haiku" in m or "4-5" in m:
            return _caps(["auto"], "Bu model API'de effort desteklemez.")
        if "4-6" in m:
            return _caps(["auto", "low", "medium", "high", "max"])
        return _caps(["auto", "low", "medium", "high", "xhigh", "max"])

    if p in ("openai",):
        levels = ["auto", "none", "low", "medium", "high"]
        if "5.2" in m or "codex-max" in m:
            levels.append("xhigh")
        return _caps(levels)

    if p == "deepseek":
        return _caps(["auto", "off", "high", "max"], "DeepSeek: off=düşünme kapalı; high/max effort.")

    if p == "nvidia":
        if "nemotron" in m:
            return _caps(["auto", "off", "low", "high"],
                         "off=düşünme kapalı, low=kısa gerekçeli, high=tam düşünme.")
        if any(k in m for k in ("glm", "qwen", "kimi", "deepseek")):
            return _caps(["auto", "off", "high"], "Bu modelde düşünme aç/kapa — ara seviye yok.")
        # Mistral/MiniMax vb: chat_template_kwargs desteği doğrulanmadı → parametre gönderme
        return _caps(["auto"], "Bu modelde reasoning kontrolü doğrulanmadı.")

    if p == "groq":
        if "gpt-oss" in m:
            return _caps(["auto", "low", "medium", "high"])
        return _caps(["auto", "off"], "Bu modelde düşünme aç/kapa.")

    if p == "z-ai":
        return _caps(["auto", "off", "high"], "GLM: düşünme aç/kapa — ara seviye yok.")

    if p in ("openrouter", "moonshot"):
        return _caps(["auto", "low", "medium", "high"], "reasoning_effort passthrough (model destekliyorsa).")

    return _caps(["auto"], "Bu sağlayıcıda reasoning kontrolü yok.")


def map_effort(provider_type: str, model_name: str, level: str) -> dict:
    """Seçilen seviyeyi ham parametreye çevir. auto/desteklenmeyen → {} (hiçbir şey gönderme)."""
    p = (provider_type or "").lower()
    m = (model_name or "").lower()
    lvl = (level or "auto").lower()

    if lvl == "auto" or lvl not in get_effort_caps(provider_type, model_name)["levels"]:
        return {}

    if p == "subscription":
        if m.startswith("claude-"):
            return {"sdk_effort": lvl}
        if m.startswith("gpt-"):
            return {"cli_config": {"model_reasoning_effort": lvl}}
        if m.startswith("copilot-"):
            return {"cli_flags": ["--effort", lvl]}
        if m.startswith("opencode:"):
            return {"opencode_reasoning": lvl}
        if m.startswith("kimi-"):
            return {}
        return {}

    if p == "google":
        if "gemini-3" in m:
            return {"gemini_thinking_level": lvl}
        budgets = {"off": 0, "low": 1024, "medium": 4096, "high": -1}  # -1 = dinamik/maks
        return {"gemini_thinking_budget": budgets.get(lvl, 4096)}

    if p == "anthropic":
        return {"anthropic_extra_body": {"output_config": {"effort": lvl}}}

    if p == "openai":
        return {"request_params": {"reasoning_effort": lvl}}

    if p == "deepseek":
        if lvl == "off":
            return {"extra_body": {"thinking": {"type": "disabled"}}}
        return {"request_params": {"reasoning_effort": lvl},
                "extra_body": {"thinking": {"type": "enabled"}}}

    if p == "nvidia":
        if "nemotron" in m:
            if lvl == "off":
                return {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
            kw: dict = {"enable_thinking": True}
            if lvl == "low":
                kw["low_effort"] = True
            return {"extra_body": {"chat_template_kwargs": kw}}
        return {"extra_body": {"chat_template_kwargs": {"enable_thinking": lvl != "off"}}}

    if p == "groq":
        if "gpt-oss" in m:
            return {"request_params": {"reasoning_effort": lvl}}
        return {"request_params": {"reasoning_effort": "none" if lvl == "off" else "default"}}

    if p == "z-ai":
        return {"extra_body": {"thinking": {"type": "disabled" if lvl == "off" else "enabled"}}}

    if p in ("openrouter", "moonshot"):
        return {"request_params": {"reasoning_effort": lvl}}

    return {}
