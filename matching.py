"""
Explainable lot <-> demand matching engine (deterministic rules, NO machine learning).

evaluate(lot, demand) checks each requirement and returns a status per check:
    pass : requirement met
    fail : requirement clearly not met
    gap  : cannot be decided because the farmer has not supplied the information/document
           (this is what makes the explanation useful: "a lab report would unlock this buyer")
Every result includes a plain-English explanation of why, so the farmer can see the reasoning.
"""
import re

UNIT_TO_QUINTAL = {"Quintal": 1.0, "Kg": 0.01, "Tonne": 10.0}
STOP = {"district", "taluka", "dist", "india", "market", "apmc", "the", "and", "near", "tal"}


def qty_q(qty, unit):
    return qty * UNIT_TO_QUINTAL.get(unit, 1.0)


def price_q(price, unit):
    """Normalise a price to Rs per quintal."""
    return price * 100 if unit == "Rs/Kg" else price


def tokens(*texts):
    out = set()
    for t in texts:
        out |= {w for w in re.findall(r"[a-z]{3,}", (t or "").lower()) if w not in STOP}
    return out


def _c(key, label, status, detail, unlock=None, short=None):
    return {"key": key, "label": label, "status": status, "detail": detail, "unlock": unlock, "short": short}


def evaluate(lot, demand):
    q = lot.quality  # may be None (no quality card yet)
    checks = []

    if demand.product_form != "Any form":
        ok = lot.product_form == demand.product_form
        checks.append(_c("form", "Product form", "pass" if ok else "fail",
                         f"Buyer wants {demand.product_form}; your lot is {lot.product_form}.",
                         short=f"form is {lot.product_form}, buyer wants {demand.product_form}"))

    have, need = qty_q(lot.quantity, lot.quantity_unit), qty_q(demand.quantity, demand.quantity_unit)
    if have >= need:
        checks.append(_c("quantity", "Quantity", "pass", f"Your lot ({have:g} q) covers the {need:g} q required."))
    else:
        checks.append(_c("quantity", "Quantity", "fail",
                         f"Your lot is {have:g} q; buyer needs {need:g} q (short by {need - have:g} q). "
                         "Combining lots with nearby farmers may cover it.",
                         short=f"lot is {need - have:g} q short"))

    ask, offer = price_q(lot.expected_price, lot.price_unit), price_q(demand.offered_price, demand.price_unit)
    if ask <= offer:
        checks.append(_c("price", "Price", "pass", f"Your expected ₹{ask:,.0f}/q is within the buyer's ₹{offer:,.0f}/q."))
    else:
        checks.append(_c("price", "Price", "fail",
                         f"You expect ₹{ask:,.0f}/q; buyer offers ₹{offer:,.0f}/q (₹{ask - offer:,.0f} lower).",
                         short=f"buyer's price is ₹{ask - offer:,.0f}/q below your expectation"))

    if demand.max_moisture is not None:
        m = q.moisture_pct if q else None
        if m is None:
            checks.append(_c("moisture", "Moisture", "gap", f"Buyer needs moisture ≤ {demand.max_moisture:g}%; yours is not declared.",
                             unlock=f"declare your lot's moisture (needs ≤ {demand.max_moisture:g}%)"))
        else:
            checks.append(_c("moisture", "Moisture", "pass" if m <= demand.max_moisture else "fail",
                             f"Buyer needs ≤ {demand.max_moisture:g}%; yours is {m:g}%.",
                             short=f"moisture {m:g}% is above {demand.max_moisture:g}%"))

    if demand.min_curcumin is not None:
        c = q.curcumin_pct if q else None
        if c is None:
            checks.append(_c("curcumin", "Curcumin", "gap",
                             f"Buyer needs curcumin ≥ {demand.min_curcumin:g}%; curcumin is not tested for your lot.",
                             unlock=f"a lab report showing curcumin ≥ {demand.min_curcumin:g}% would unlock this buyer"))
        elif c < demand.min_curcumin:
            checks.append(_c("curcumin", "Curcumin", "fail",
                             f"Buyer needs ≥ {demand.min_curcumin:g}%; your lot shows {c:g}%.",
                             short=f"curcumin {c:g}% is below {demand.min_curcumin:g}%"))
        elif q.has_lab_report:
            checks.append(_c("curcumin", "Curcumin", "pass", f"Lab-reported {c:g}% meets ≥ {demand.min_curcumin:g}%."))
        else:
            checks.append(_c("curcumin", "Curcumin", "gap",
                             f"You declared {c:g}%, which meets ≥ {demand.min_curcumin:g}%, but there is no lab report to prove it.",
                             unlock="upload/attach a lab report to confirm your declared curcumin"))

    if demand.requires_lab_report:
        has = bool(q and q.has_lab_report)
        checks.append(_c("lab", "Lab report", "pass" if has else "gap",
                         "Lab report available." if has else "Buyer requires a lab report; your lot has none.",
                         unlock="get a lab report for this lot"))

    if demand.deliver_by:
        a = lot.availability_date
        if a is None:
            checks.append(_c("timing", "Availability", "gap", f"Buyer needs delivery by {demand.deliver_by:%d %b %Y}; your availability date is not set.",
                             unlock="set the date your lot is available"))
        else:
            checks.append(_c("timing", "Availability", "pass" if a <= demand.deliver_by else "fail",
                             f"Available {a:%d %b %Y}; buyer needs delivery by {demand.deliver_by:%d %b %Y}.",
                             short=f"available {a:%d %b}, after the {demand.deliver_by:%d %b} deadline"))

    overlap = tokens(lot.location) & tokens(demand.delivery_location)
    if overlap:
        checks.append(_c("location", "Location", "pass", f"Lot location ({lot.location}) overlaps delivery area ({demand.delivery_location})."))
    else:
        checks.append(_c("location", "Location", "gap",
                         f"Lot is in {lot.location}; delivery is in {demand.delivery_location}. Transport has to be agreed.",
                         unlock="agree transport with the buyer"))

    met = sum(c["status"] == "pass" for c in checks)
    fails = [c for c in checks if c["status"] == "fail"]
    gaps = [c for c in checks if c["status"] == "gap"]
    text = [f"Your lot meets {met} of {len(checks)} requirements."]
    if gaps:
        text.append("To improve this match: " + "; ".join(g["unlock"] for g in gaps) + ".")
    if fails:
        text.append("Does not meet: " + "; ".join(f["short"] for f in fails) + ".")
    if not fails and not gaps:
        text.append("All requirements are met.")
    only_qty = bool(fails) and all(f["key"] == "quantity" for f in fails)
    label = ("Strong match" if not fails and not gaps else "Possible match" if not fails
             else "Group lots needed" if only_qty else "Weak match")
    return {"checks": checks, "met": met, "total": len(checks), "score": met / len(checks),
            "fail_keys": {f["key"] for f in fails}, "explanation": " ".join(text), "label": label}


def _rank_key(item):
    ev = item["eval"]
    return (len(ev["fail_keys"]), -ev["score"])


def rank_demands_for_lot(lot, demands):
    return sorted(({"demand": d, "eval": evaluate(lot, d)} for d in demands), key=_rank_key)


def rank_lots_for_demand(demand, lots):
    return sorted(({"lot": l, "eval": evaluate(l, demand)} for l in lots), key=_rank_key)


def direct_offers(ranked):
    """Open demands the lot could realistically serve (hard mismatches other than price/quantity excluded)."""
    out = []
    for r in ranked:
        if r["eval"]["fail_keys"] <= {"price", "quantity"}:
            d = r["demand"]
            out.append({"demand": d, "offer_q": price_q(d.offered_price, d.price_unit),
                        "covers_qty": "quantity" not in r["eval"]["fail_keys"]})
    return sorted(out, key=lambda o: -o["offer_q"])


def group_suggestion(demand, lots):
    """Combine lots that fail ONLY on quantity until the demand's quantity is covered. Farmers must agree."""
    need = qty_q(demand.quantity, demand.quantity_unit)
    cands = []
    for l in lots:
        ev = evaluate(l, demand)
        if ev["fail_keys"] <= {"quantity"} and "quantity" in ev["fail_keys"]:
            cands.append((qty_q(l.quantity, l.quantity_unit), l))
    cands.sort(key=lambda x: -x[0])
    chosen, total = [], 0.0
    for q, l in cands:
        chosen.append(l)
        total += q
        if total >= need:
            return {"lots": chosen, "total_q": total, "need_q": need}
    return None
