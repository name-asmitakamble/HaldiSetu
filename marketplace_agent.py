"""Marketplace agent: observe -> decide (LLM) -> act (tools) -> repeat.

If the LLM is unavailable or errors, a deterministic fallback still creates matches.
Uses the Anthropic SDK directly. If your llm.py already wraps a client, you can swap
`_client()` to use it.
"""
import json
import os
from datetime import datetime

from models import db  # adjust if needed
from models_agent import AgentRun, AgentAction, MatchProposal
from agent_notifications import notify_user
import agent_tools as T

MODEL = os.getenv("AGENT_MODEL", "claude-sonnet-5-5")
MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "8"))
MIN_PROPOSE_SCORE = float(os.getenv("AGENT_MIN_SCORE", "60"))

SYSTEM_PROMPT = """You are the HaldiSetu Marketplace Agent for turmeric farmers and buyers in India.
GOAL: get every available lot sold at a fair price to a suitable buyer, and every requirement fulfilled.

You may: search candidates, score matches, look up market price and schemes, propose matches, send notifications.
You may NOT: accept deals, reveal phone numbers or contact details, or change any price. Users decide.

Rules:
- Never invent numbers. Scores, prices and quantities must come from tool results.
- Only propose matches with score >= 60. Do not spam: at most 3 proposals per run.
- Explanations: 1-2 short, simple sentences (product form, quantity, price vs offered price, quality, location).
- find_candidates already excludes pairs that fail any requirement; scores are computed by code.
- Write each notification in the user's language (en, hi, mr). Use simple words for farmers.
- If market price data is available and the lot's price is far above it, mention that gently.
- When done, reply with a one-line summary of what you did."""

 
def _client():
    import anthropic
    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from environment

 
def _log(run_id, name, inp, out):
    db.session.add(AgentAction(run_id=run_id, tool_name=name,
                               tool_input=json.dumps(inp, default=str)[:4000],
                               tool_output=json.dumps(out, default=str)[:4000]))
    db.session.commit()

 
def _run_llm(run, event):
    client = _client()
    messages = [{"role": "user", "content":
                 f"Event: {json.dumps(event)}. Find matches and take appropriate actions."}]
    for _ in range(MAX_STEPS):
        resp = client.messages.create(model=MODEL, max_tokens=1000, system=SYSTEM_PROMPT,
                                      tools=T.TOOL_SCHEMAS, messages=messages)
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text")
        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            fn = T.TOOLS.get(block.name)
            try:
                out = fn(**block.input) if fn else {"error": "unknown tool"}
            except Exception as e:  # tool errors go back to the model, not the user
                db.session.rollback()
                out = {"error": str(e)}
            _log(run.id, block.name, block.input, out)
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": json.dumps(out, default=str)})
        messages.append({"role": "user", "content": results})
    return "Stopped: step limit reached."

 
def _explain(c, entity_type):
    """Plain, factual one-liner built only from numbers the matching engine returned."""
    bits = [f"{c['label']}: meets {c['met']} of {c['total']} requirements"]
    if entity_type == "lot":
        bits.append(f"{c['industry']} wants {c['quantity']:g} {c['unit']} at Rs {c['offered_price_per_q']:,.0f}/q")
    else:
        bits.append(f"{c['product_form']} lot, {c['quantity']:g} {c['unit']} at Rs {c['price_per_q']:,.0f}/q")
    if c.get("unlock"):
        bits.append("to improve: " + c["unlock"][0])
    return ". ".join(bits) + "."


def _run_deterministic(run, event):
    """No-LLM fallback: propose the top matches with a templated explanation."""
    res = T.find_candidates(event["entity_type"], event["entity_id"], min_score=MIN_PROPOSE_SCORE, limit=3)
    _log(run.id, "find_candidates", event, res)
    n = 0
    for c in res.get("candidates", []):
        if event["entity_type"] == "lot":
            lot_id, req_id = event["entity_id"], c["requirement_id"]
        else:
            lot_id, req_id = c["lot_id"], event["entity_id"]
        out = T.propose_match(lot_id, req_id, _explain(c, event["entity_type"]))
        _log(run.id, "propose_match", {"lot_id": lot_id, "requirement_id": req_id}, out)
        n += 1
    return f"Fallback mode: proposed {n} match(es)."

 
def run_agent(event):
    """event = {"trigger": "new_lot", "entity_type": "lot", "entity_id": 12}
    Must be called inside a Flask app context."""
    run = AgentRun(trigger=event.get("trigger"), entity_type=event.get("entity_type"),
                   entity_id=event.get("entity_id"), mode="llm")
    db.session.add(run)
    db.session.commit()
    try:
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError("no API key")
        summary = _run_llm(run, event)
        # Safety net: the LLM is optional help, a good match must never be lost because it skipped a step.
        if not MatchProposal.query.filter(
                (MatchProposal.lot_id == event["entity_id"]) if event["entity_type"] == "lot"
                else (MatchProposal.requirement_id == event["entity_id"])).first():
            extra = _run_deterministic(run, event)
            summary += f" | {extra}"
    except Exception as e:
        db.session.rollback()
        run.mode = "deterministic"
        db.session.commit()
        try:
            summary = _run_deterministic(run, event) + f" (LLM unavailable: {e})"
        except Exception as e2:
            db.session.rollback()
            run.status, run.summary = "failed", str(e2)
            run.finished_at = datetime.utcnow()
            db.session.commit()
            return run
    run.status, run.summary, run.finished_at = "done", summary, datetime.utcnow()
    db.session.commit()
    return run
 