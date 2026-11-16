"""
Scheme agent. Pipeline (each step is deterministic and explainable):
  1. read the saved FarmerProfile                    (tool: database)
  2. evaluate every scheme's eligibility rules       (tool: scheme_engine — rule-based, NOT an LLM)
  3. compare required documents with what the farmer has
  4. check which farming stage each scheme is useful in
  5. explain in the farmer's language (stored, reviewed text) + build a personal action calendar
Eligibility is NEVER decided by free-text AI. Final approval always rests with the government authority.
"""
import json

from i18n import STAGE_ORDER, STAGES, check_text, fmt
from models import Scheme
from models_market import SchemeInfo
from scheme_content import apply_url_for, apply_hint_for
from scheme_engine import evaluate


def _j(text, default):
    try:
        return json.loads(text) if text else default
    except json.JSONDecodeError:
        return default


def _loc(d, lang, fallback=""):
    return d.get(lang) or d.get("en") or fallback


def profile_dict(fp):
    return {"state": fp.state or "", "land_ha": fp.land_ha, "owns_land": (fp.owns_land or "").lower(),
            "farmer_type": (fp.farmer_type or "").lower()}


def run(fp, lang="en"):
    """Returns dict(results=[...], calendar=[...], summary=str)."""
    profile, have = profile_dict(fp), set(_j(fp.docs, []))
    results = []
    for s in Scheme.query.order_by(Scheme.scheme_name).all():
        info = SchemeInfo.query.filter_by(scheme_id=s.scheme_id).first()
        status, checks = evaluate(_j(s.eligibility_rules, {}), profile)
        stages = _j(info.stages, []) if info else []
        need = _j(info.required_docs, []) if info else []
        results.append({
            "scheme": s, "status": status, "apply_url": apply_url_for(s), "apply_hint": apply_hint_for(s, lang),
            "name": _loc(_j(info.names, {}), lang, s.scheme_name) if info else s.scheme_name,
            "highlights": _loc(_j(info.highlights, {}), lang, s.description) if info else s.description,
            "steps": _loc(_j(info.steps, {}), lang, []) if info else [],
            "checks": [{"text": check_text(c["label"], c["result"], lang), "result": c["result"]} for c in checks],
            "note": _j(s.eligibility_rules, {}).get("note"),
            "stages": stages, "relevant_now": (not stages) or fp.stage in stages,
            "stage_names": [STAGES[k][lang] for k in stages if k in STAGES],
            "need_docs": need, "have_docs": [d for d in need if d in have], "missing_docs": [d for d in need if d not in have],
        })
    order = {"match": 0, "unknown": 1, "no": 2}
    results.sort(key=lambda r: (order[r["status"]], not r["relevant_now"], r["scheme"].scheme_name))

    calendar = []
    for stage in STAGE_ORDER:
        items = [r for r in results if r["status"] != "no" and stage in r["stages"]]
        if items:
            calendar.append({"stage": stage, "label": STAGES[stage][lang], "current": stage == fp.stage,
                             "items": [{"name": r["name"], "have": len(r["have_docs"]), "need": len(r["need_docs"])} for r in items]})
    ok = [r for r in results if r["status"] != "no"]
    now = [r for r in ok if r["relevant_now"]]
    return {"results": results, "calendar": calendar, "summary": fmt(lang, "summary", n=len(ok), now=len(now))}