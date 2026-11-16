"""
Optional Claude access for LANGUAGE and DOCUMENT-READING tasks only.

  Used for : understanding Marathi/Hindi lot descriptions, polishing negotiation drafts, reading proof documents.
  NEVER for: eligibility, match scores, prices or approvals — those stay rule-based / human (project plan).

Enabled only when ANTHROPIC_API_KEY is set in .env. Every function returns None on ANY problem (no key, no
network, bad JSON), and every caller has a rule-based fallback, so the app works fully without it.
    pip install anthropic          (optional)
    ANTHROPIC_API_KEY=sk-ant-...   ANTHROPIC_MODEL=claude-sonnet-5-5   (model name is configurable)
"""
import base64
import json
import os
import re


def available():
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())


def complete(system, user, max_tokens=700, image=None):
    """image = (media_type, bytes) or None. Returns text, or None on any failure."""
    if not available():
        return None
    try:
        import anthropic

        content = [{"type": "text", "text": user}]
        if image:
            content.insert(0, {"type": "image", "source": {"type": "base64", "media_type": image[0],
                                                           "data": base64.b64encode(image[1]).decode()}})
        client = anthropic.Anthropic()
        r = client.messages.create(model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5"), max_tokens=max_tokens,
                                   system=system, messages=[{"role": "user", "content": content}])
        return "".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip() or None
    except Exception:  # noqa: BLE001 — a failing AI call must never break the app
        return None


def complete_json(system, user, max_tokens=700, image=None):
    text = complete(system, user, max_tokens, image)
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        return json.loads(m.group(0)) if m else None
    except ValueError:
        return None
