"""Tools the marketplace agent can call.
 
RULE: numbers (scores, prices) come only from code here, never from the LLM.
 
SECTION 1 is the ONLY part you should need to adapt to your existing project.
"""
import json
import math
 
from models import db  # adjust if needed
from models_agent import MatchProposal
from agent_notifications import notify_user
 
# ----------------------------------------------------------------------------
# SECTION 1: ADAPTERS to the real HaldiSetu models
# ----------------------------------------------------------------------------
from models import ProductListing
from models_market import BuyerDemand, DemandResponse
from matching import evaluate, price_q, qty_q

Lot = ProductListing
Requirement = BuyerDemand

LOT_OPEN_STATUSES = ["open"]       # ProductListing.listing_status values meaning "still for sale"
REQ_OPEN_STATUSES = ["open"]       # BuyerDemand.status values meaning "still needed"


def _lot_id(lot):
    return lot.listing_id


def _req_id(req):
    return req.demand_id


def _user_language(user_id):
    """Farmers keep a language on their profile; buyers default to English."""
    try:
        from models_market import FarmerProfile
        fp = FarmerProfile.query.filter_by(user_id=user_id).first()
        return fp.language if fp and fp.language in ("en", "mr", "hi") else "en"
    except Exception:
        return "en"


def _price_lookup(variety, district):
    """Mandi baseline in Rs/quintal from the latest imported market prices (price_engine)."""
    try:
        import price_engine
        base = price_engine.baseline_for_location(district or "")
        return {"available": bool(base), "data": base}
    except Exception as e:
        return {"available": False, "error": str(e)}


def _scheme_lookup(farmer_id):
    """Scheme matching needs the farmer profile; the agent only reports that schemes exist."""
    return {"available": False, "error": "scheme matching is done on the farmer's Schemes page"}


# ----------------------------------------------------------------------------
# SECTION 2: DETERMINISTIC MATCHING = the project's own explainable engine (matching.py)
# The score is computed here, in code. The LLM never invents or changes it.
# ----------------------------------------------------------------------------
def score_pair(lot, req):
    """Returns {accepted, score(0-100), breakdown, rejected_reason}.
    A hard FAIL on any check (form, quantity, price, curcumin, moisture, timing) rejects the pair.
    A GAP (information the farmer has not supplied yet, e.g. lab report) counts half."""
    ev = evaluate(lot, req)
    total = max(ev["total"], 1)
    gaps = [c for c in ev["checks"] if c["status"] == "gap"]
    breakdown = {c["key"]: c["status"] for c in ev["checks"]}
    if ev["fail_keys"]:
        return {"accepted": False, "score": 0, "breakdown": breakdown,
                "rejected_reason": "does not meet: " + ", ".join(sorted(ev["fail_keys"]))}
    score = round(100 * (ev["met"] + 0.5 * len(gaps)) / total, 1)
    return {"accepted": True, "score": score, "breakdown": breakdown, "rejected_reason": None,
            "met": ev["met"], "total": ev["total"], "label": ev["label"],
            "unlock": [c["unlock"] for c in gaps if c.get("unlock")]}


# ----------------------------------------------------------------------------
# SECTION 3: TOOL FUNCTIONS
# ----------------------------------------------------------------------------
def _lot_dict(lot):
    q = lot.quality
    return {"lot_id": _lot_id(lot), "farmer_id": lot.farmer_id, "product_form": lot.product_form,
            "variety": q.variety if q else None, "quantity": lot.quantity, "unit": lot.quantity_unit,
            "quantity_q": qty_q(lot.quantity, lot.quantity_unit),
            "price_per_q": price_q(lot.expected_price, lot.price_unit),
            "curcumin": q.curcumin_pct if q else None, "moisture": q.moisture_pct if q else None,
            "has_lab_report": bool(q and q.has_lab_report), "location": lot.location}


def _req_dict(req):
    return {"requirement_id": _req_id(req), "buyer_id": req.buyer_id, "industry": req.industry_type,
            "product_form": req.product_form, "quantity": req.quantity, "unit": req.quantity_unit,
            "quantity_q": qty_q(req.quantity, req.quantity_unit),
            "offered_price_per_q": price_q(req.offered_price, req.price_unit),
            "min_curcumin": req.min_curcumin, "max_moisture": req.max_moisture,
            "requires_lab_report": bool(req.requires_lab_report), "delivery_location": req.delivery_location}


def _already_offered(lot_id, req_id):
    return DemandResponse.query.filter_by(listing_id=lot_id, demand_id=req_id).first() is not None


def find_candidates(entity_type, entity_id, min_score=40, limit=5):
    """Given a lot, return best open requirements (or vice versa), already scored by code."""
    out = []
    if entity_type == "lot":
        lot = db.session.get(Lot, entity_id)
        if not lot:
            return {"error": "lot not found"}
        for req in Requirement.query.filter(Requirement.status.in_(REQ_OPEN_STATUSES)).all():
            s = score_pair(lot, req)
            if s["accepted"] and s["score"] >= min_score and not _already_offered(_lot_id(lot), _req_id(req)):
                out.append({**_req_dict(req), **s})
    elif entity_type == "requirement":
        req = db.session.get(Requirement, entity_id)
        if not req:
            return {"error": "requirement not found"}
        for lot in Lot.query.filter(Lot.listing_status.in_(LOT_OPEN_STATUSES)).all():
            s = score_pair(lot, req)
            if s["accepted"] and s["score"] >= min_score and not _already_offered(_lot_id(lot), _req_id(req)):
                out.append({**_lot_dict(lot), **s})
    else:
        return {"error": "entity_type must be 'lot' or 'requirement'"}
    out.sort(key=lambda x: x["score"], reverse=True)
    return {"candidates": out[:limit], "count": len(out)}
 
 
def score_match(lot_id, requirement_id):
    lot, req = db.session.get(Lot, lot_id), db.session.get(Requirement, requirement_id)
    if not lot or not req:
        return {"error": "lot or requirement not found"}
    return score_pair(lot, req)
 
 
def get_market_price(variety, district=None):
    return _price_lookup(variety, district)
 
 
def check_schemes(farmer_id):
    return _scheme_lookup(farmer_id)
 
 
def propose_match(lot_id, requirement_id, explanation, language_farmer="en", language_buyer="en"):
    """Saves a proposal and notifies BOTH sides. Score is recomputed here, any LLM value is ignored.
    Does NOT accept a deal and does NOT reveal any phone number: contacts are shared only after
    the farmer confirms a deal (deals.py)."""
    lot, req = db.session.get(Lot, lot_id), db.session.get(Requirement, requirement_id)
    if not lot or not req:
        return {"error": "lot or requirement not found"}
    s = score_pair(lot, req)
    if not s["accepted"]:
        return {"error": f"rejected by filter: {s['rejected_reason']}"}
    existing = MatchProposal.query.filter_by(lot_id=lot_id, requirement_id=requirement_id).first()
    if existing or _already_offered(lot_id, requirement_id):
        return {"ok": True, "already_proposed": True, "proposal_id": existing.id if existing else None}
    explanation = (explanation or "").strip()[:280] or f"{s['label']}: meets {s['met']} of {s['total']} requirements."
    p = MatchProposal(lot_id=lot_id, requirement_id=requirement_id, score=s["score"],
                      breakdown=json.dumps(s["breakdown"]), explanation=explanation)
    db.session.add(p)
    db.session.commit()
    notify_user(lot.farmer_id, f"AI match ({s['score']:.0f}/100): {explanation} Open AI Matches to offer your lot.",
                _user_language(lot.farmer_id), "match")
    notify_user(req.buyer_id, f"AI match ({s['score']:.0f}/100): {explanation} Open AI Matches to review it.",
                _user_language(req.buyer_id), "match")
    return {"ok": True, "proposal_id": p.id, "score": s["score"]}


def send_notification(user_id, message, language="en"):
    return notify_user(user_id, message, language, "agent")
 
 
TOOLS = {
    "find_candidates": find_candidates,
    "score_match": score_match,
    "get_market_price": get_market_price,
    "check_schemes": check_schemes,
    "propose_match": propose_match,
    "send_notification": send_notification,
}
 
TOOL_SCHEMAS = [
    {"name": "find_candidates",
     "description": "Find best matching open requirements for a lot, or open lots for a requirement. Scores are computed by code.",
     "input_schema": {"type": "object", "properties": {
         "entity_type": {"type": "string", "enum": ["lot", "requirement"]},
         "entity_id": {"type": "integer"},
         "min_score": {"type": "number"}, "limit": {"type": "integer"}},
         "required": ["entity_type", "entity_id"]}},
    {"name": "score_match", "description": "Score one lot against one requirement (0-100 with breakdown).",
     "input_schema": {"type": "object", "properties": {
         "lot_id": {"type": "integer"}, "requirement_id": {"type": "integer"}},
         "required": ["lot_id", "requirement_id"]}},
    {"name": "get_market_price", "description": "Current market (mandi) price for a turmeric variety.",
     "input_schema": {"type": "object", "properties": {
         "variety": {"type": "string"}, "district": {"type": "string"}}, "required": ["variety"]}},
    {"name": "check_schemes", "description": "Government schemes relevant to a farmer.",
     "input_schema": {"type": "object", "properties": {"farmer_id": {"type": "integer"}},
                      "required": ["farmer_id"]}},
    {"name": "propose_match",
     "description": "Propose a match to both farmer and buyer. Only call for good matches (score >= 60). "
                    "Explanation must be short, simple, and use only facts returned by tools.",
     "input_schema": {"type": "object", "properties": {
         "lot_id": {"type": "integer"}, "requirement_id": {"type": "integer"},
         "explanation": {"type": "string"},
         "language_farmer": {"type": "string"}, "language_buyer": {"type": "string"}},
         "required": ["lot_id", "requirement_id", "explanation"]}},
    {"name": "send_notification", "description": "Send an in-app message to one user.",
     "input_schema": {"type": "object", "properties": {
         "user_id": {"type": "integer"}, "message": {"type": "string"}, "language": {"type": "string"}},
         "required": ["user_id", "message"]}},
]
 