"""
Negotiation agent: drafts the farmer's message and suggests a counter-offer ABOVE the farmer's minimum price.

All numbers come from data on the page (the farmer's ask/minimum, the buyer's offer, the mandi floor).
The counter-offer rule is deliberately simple and explained to the farmer:
    buyer offer >= your ask      -> accept the offer
    otherwise                    -> meet in the middle, rounded to Rs 50, never below your minimum, never above your ask
The farmer edits and approves the draft; HaldiSetu never sends anything by itself. Claude (optional) only polishes wording
and its output is rejected unless every number survives.
"""
import re

import llm
from matching import price_q

UNIT_MR = {"Quintal": "क्विंटल", "Kg": "किलो", "Tonne": "टन"}
FORM_MR = {"Fresh rhizome": "ओली हळद", "Dried turmeric (finger)": "वाळलेली हळद (हळकुंड)",
           "Dried turmeric (bulb)": "वाळलेली हळद (गड्डा)", "Polished turmeric": "पॉलिश हळद", "Turmeric powder": "हळद पावडर"}
MAX_LEN = 300     # DemandResponse.message limit


def _r50(x):
    return round(x / 50.0) * 50


def counter_offer(ask, offer, minimum=None):
    """Returns (counter Rs/q, list of reasons)."""
    reasons = []
    if offer >= ask:
        reasons.append(f"The buyer's offer (₹{offer:,.0f}) already meets your asking price (₹{ask:,.0f}).")
        return offer, reasons
    mid = _r50((offer + ask) / 2)
    counter = min(max(mid, minimum or 0), ask)
    if minimum is not None and minimum > ask:
        reasons.append("Your minimum is above your asking price — check both numbers.")
    reasons.append(f"The buyer offers ₹{offer:,.0f}; you ask ₹{ask:,.0f}. Meeting in the middle gives ₹{mid:,.0f}.")
    if minimum is not None and counter == minimum and minimum > mid:
        reasons.append(f"Raised to your minimum price of ₹{minimum:,.0f}.")
    return counter, reasons


def _message(lot, demand, counter, base, lang, farmer_name):
    q = lot.quality
    avail = f"{lot.availability_date:%d %b %Y}" if lot.availability_date else None
    if lang == "mr":
        parts = [f"नमस्कार. मी {lot.location} येथून {lot.quantity:g} {UNIT_MR.get(lot.quantity_unit, lot.quantity_unit)} "
                 f"{FORM_MR.get(lot.product_form, lot.product_form)} देऊ शकतो."]
        if avail:
            parts.append(f"माल {avail} पासून उपलब्ध.")
        qual = []
        if q and q.moisture_pct is not None:
            qual.append(f"ओलावा {q.moisture_pct:g}%")
        if q and q.curcumin_pct is not None:
            qual.append(f"कर्क्युमिन {q.curcumin_pct:g}%" + (" (लॅब रिपोर्टसह)" if q.has_lab_report else ""))
        if qual:
            parts.append(", ".join(qual) + ".")
        parts.append(f"माझा दर ₹{counter:,.0f} प्रति क्विंटल.")
        if base:
            parts.append(f"बाजार संदर्भ: ₹{base['modal']:,.0f} ({base['latest']:%d %b}).")
        parts.append(f"कृपया कळवा. - {farmer_name}")
    else:
        parts = [f"Namaste. I can supply {lot.quantity:g} {lot.quantity_unit} of {lot.product_form} from {lot.location}."]
        if avail:
            parts.append(f"Available from {avail}.")
        qual = []
        if q and q.moisture_pct is not None:
            qual.append(f"moisture {q.moisture_pct:g}%")
        if q and q.curcumin_pct is not None:
            qual.append(f"curcumin {q.curcumin_pct:g}%" + (" (lab report available)" if q.has_lab_report else " (declared)"))
        if qual:
            parts.append("Quality: " + ", ".join(qual) + ".")
        parts.append(f"My price is ₹{counter:,.0f} per quintal.")
        if base:
            parts.append(f"Mandi reference: ₹{base['modal']:,.0f} ({base['latest']:%d %b}).")
        parts.append(f"Please reply if this suits you. - {farmer_name}")
    # keep within the response limit by dropping optional sentences from the end of the middle
    while len(" ".join(parts)) > MAX_LEN and len(parts) > 3:
        parts.pop(-2)
    return " ".join(parts)[:MAX_LEN]


def _polish(msg, lang):
    out = llm.complete(
        "Rewrite this message that a turmeric farmer will send to an industry buyer. Same language (" +
        ("Marathi" if lang == "mr" else "English") + "), polite and clear, at most 280 characters. "
        "Keep every number exactly as written. Reply with only the message.", msg, max_tokens=300)
    if not out or len(out) > MAX_LEN:
        return msg, False
    if set(re.findall(r"\d[\d,\.]*", msg)) - set(re.findall(r"\d[\d,\.]*", out)):
        return msg, False                      # a number was lost or changed -> reject the rewrite
    return out, True


def draft(lot, demand, price, ev, minimum=None, lang="en"):
    lang = lang if lang in ("en", "mr") else "en"
    ask, offer = price_q(lot.expected_price, lot.price_unit), price_q(demand.offered_price, demand.price_unit)
    counter, reasons = counter_offer(ask, offer, minimum)
    base, floor = price.get("base"), price.get("floor")
    if floor and counter < floor:
        reasons.append(f"Warning: ₹{counter:,.0f} is below the mandi's reported minimum (≈ ₹{floor:,.0f}). Compare more buyers.")
    if price.get("estimate"):
        reasons.append(f"Your lot's estimated price from mandi data is ₹{price['estimate']:,.0f}.")
    if ev["fail_keys"] - {"price"}:
        reasons.append("This lot does not meet all of the buyer's requirements — see the match explanation before offering.")
    msg = _message(lot, demand, counter, base, lang, lot.farmer.name)
    msg, polished = _polish(msg, lang) if llm.available() else (msg, False)
    return {"counter": counter, "ask": ask, "offer": offer, "minimum": minimum, "reasons": reasons,
            "message": msg, "lang": lang, "polished_by_llm": polished}
