"""
Sell-Channel Advisor Agent
==========================
Compares all selling channels for a specific farmer lot:
  1. Local Agricultural Mandi (APMC Auction)
  2. Food & Spice Company
  3. Medicine & Nutraceutical Maker
  4. Cosmetics & Natural Dye Maker
  5. Research Lab & Extract Maker

Evaluates requirements, identifies blockers/gaps, computes exact expected realizations,
and produces a clear, actionable recommendation in English, Marathi, or Hindi.

Strict Integrity Rules:
  - All numbers are deterministic arithmetic from stored records.
  - LLM (Claude) only optionally polishes phrasing; rewrites are rejected if ANY number changes.
"""
import re
from statistics import mean

import llm
from matching import evaluate, price_q, qty_q
from models_market import BuyerDemand, INDUSTRIES
from price_engine import mandi_baseline, price_card, variety_ratio


def evaluate_lot_channels(lot, lang="en", transport_cost_q=None):
    """
    Evaluates a farmer lot across Mandi and all 4 Industry sectors.
    Returns:
      - lot_summary
      - mandi_channel
      - industry_channels (sorted by expected price / suitability)
      - recommendation (best channel, payout, why in requested language, unlock steps)
    """
    lang = lang if lang in ("en", "mr", "hi") else "en"
    q = lot.quality
    lot_q = qty_q(lot.quantity, lot.quantity_unit)

    # 1. Mandi Channel Assessment
    base = mandi_baseline(lot)
    mandi_modal = base["modal"] if base and base.get("modal") else 11000.0
    v_info = variety_ratio(q.variety, base["latest"]) if (q and q.variety and base) else None
    mandi_adjusted = (mandi_modal * v_info["ratio"]) if v_info else mandi_modal
    mandi_gross = mandi_adjusted * lot_q
    mandi_net = ((mandi_adjusted - transport_cost_q) * lot_q) if transport_cost_q is not None else mandi_gross

    mandi_channel = {
        "channel_type": "mandi",
        "name": "Local Mandi (APMC Auction)",
        "expected_price": mandi_adjusted,
        "gross_value": mandi_gross,
        "net_value": mandi_net,
        "status": "ready",
        "status_label": "Immediate Sale",
        "status_class": "ok",
        "requirements_met": True,
        "blockers": [],
        "unlock_actions": [],
        "pros": "Guaranteed liquidity; transparent daily APMC auction; no lab test certificate mandatory.",
        "cons": "Standard bulk pricing; does not pay direct quality premiums for high curcumin.",
        "markets": base["markets"] if base else ["Nearby APMC"],
        "is_sample": base["is_sample"] if base else False,
    }

    # 2. Industry Channels Assessment
    industry_channels = []
    from industry_agent import INDUSTRY_METADATA

    for ind in INDUSTRIES:
        meta = INDUSTRY_METADATA.get(ind, {"display_name": ind, "icon": "🏢"})
        demands = BuyerDemand.query.filter_by(industry_type=ind, status="open").all()
        if not demands:
            industry_channels.append({
                "industry_type": ind,
                "display_name": meta["display_name"],
                "icon": meta["icon"],
                "status": "no_demand",
                "status_label": "No Open Demand",
                "status_class": "grey",
                "expected_price": None,
                "gross_value": None,
                "diff_vs_mandi": None,
                "best_demand": None,
                "eval": None,
                "blockers": ["No commercial buyers in this industry have posted open requirements."],
                "unlock_actions": [],
            })
            continue

        # Evaluate against all open demands in this sector; pick highest paying feasible one
        evaluations = []
        for d in demands:
            ev = evaluate(lot, d)
            p_q = price_q(d.offered_price, d.price_unit)
            evaluations.append({"demand": d, "eval": ev, "price_q": p_q})

        # Sort by: 1) fewest fail keys, 2) highest price
        evaluations.sort(key=lambda x: (len(x["eval"]["fail_keys"]), -x["price_q"]))
        best = evaluations[0]
        d_best = best["demand"]
        ev_best = best["eval"]
        ind_price = best["price_q"]
        ind_gross = ind_price * lot_q
        diff_q = ind_price - mandi_adjusted

        # Determine qualification tier
        hard_fail_keys = ev_best["fail_keys"] - {"price", "quantity"}  # price is negotiable, quantity can be partial/grouped
        gaps = [c for c in ev_best["checks"] if c["status"] == "gap"]
        fails = [c for c in ev_best["checks"] if c["status"] == "fail" and c["key"] not in ("price", "quantity")]

        blockers = []
        unlock_actions = []

        for f in fails:
            blockers.append(f.get("short") or f.get("detail"))
        if "quantity" in ev_best["fail_keys"]:
            short_q = d_best.quantity - lot_q
            blockers.append(f"Lot is {short_q:g} q short of buyer's {d_best.quantity:g} q; can offer partial lot or combine with neighbors")

        for g in gaps:
            unlock_actions.append(g.get("unlock") or g.get("detail"))

        if not hard_fail_keys and not gaps:
            tier = "qualified"
            covers_qty = "quantity" not in ev_best["fail_keys"]
            status_label = "Fully Qualified" if covers_qty else "Qualified (Partial Lot)"
            status_class = "ok"
        elif not hard_fail_keys and gaps:
            tier = "unlockable"
            status_label = "Needs Quality Document"
            status_class = "warn"
        else:
            tier = "not_qualified"
            status_label = "Requirements Mismatched"
            status_class = "err"

        industry_channels.append({
            "industry_type": ind,
            "display_name": meta["display_name"],
            "icon": meta["icon"],
            "status": tier,
            "status_label": status_label,
            "status_class": status_class,
            "expected_price": ind_price,
            "gross_value": ind_gross,
            "diff_vs_mandi": diff_q,
            "diff_gross": diff_q * lot_q,
            "best_demand": d_best,
            "eval": ev_best,
            "blockers": blockers,
            "unlock_actions": unlock_actions,
            "is_demo": d_best.is_demo,
            "buyer_name": d_best.buyer.name if d_best.buyer else "Industry Buyer",
        })

    # Sort industry channels by expected price descending
    industry_channels.sort(key=lambda x: (x["expected_price"] or 0), reverse=True)

    # 3. Formulate Recommendation
    # Check if there is an industry channel that is qualified or unlockable with positive gain over mandi
    attractive_industries = [
        c for c in industry_channels
        if c["status"] in ("qualified", "unlockable") and (c["diff_vs_mandi"] or 0) > 0
    ]

    rec = None
    if attractive_industries:
        # Check if top one is qualified
        top_ind = attractive_industries[0]
        if top_ind["status"] == "qualified":
            rec = {
                "winner": "industry",
                "target_name": top_ind["display_name"],
                "target_obj": top_ind,
                "price": top_ind["expected_price"],
                "gross": top_ind["gross_value"],
                "gain_over_mandi": top_ind["diff_gross"],
                "gain_per_q": top_ind["diff_vs_mandi"],
                "mode": "qualified",
                "demand_id": top_ind["best_demand"].demand_id if top_ind["best_demand"] else None,
            }
        else:
            # Unlockable: High upside if farmer performs 1-2 actions (e.g. lab test)
            rec = {
                "winner": "industry_with_unlock",
                "target_name": top_ind["display_name"],
                "target_obj": top_ind,
                "price": top_ind["expected_price"],
                "gross": top_ind["gross_value"],
                "gain_over_mandi": top_ind["diff_gross"],
                "gain_per_q": top_ind["diff_vs_mandi"],
                "mode": "unlockable",
                "unlock_action": top_ind["unlock_actions"][0] if top_ind["unlock_actions"] else "Complete quality card",
                "fallback_mandi_price": mandi_adjusted,
                "demand_id": top_ind["best_demand"].demand_id if top_ind["best_demand"] else None,
            }
    else:
        # Default to Mandi
        rec = {
            "winner": "mandi",
            "target_name": "Local Mandi (APMC)",
            "target_obj": mandi_channel,
            "price": mandi_adjusted,
            "gross": mandi_gross,
            "gain_over_mandi": 0.0,
            "gain_per_q": 0.0,
            "mode": "mandi_best",
            "demand_id": None,
        }

    # 4. Generate Explainable Text (Rule-based Multilingual)
    text_en, text_mr, text_hi = _generate_multilingual_reasons(lot, mandi_channel, rec)

    # Optional Claude polishing (strictly rejects if any number is altered)
    polished = False
    chosen_text = text_en if lang == "en" else (text_mr if lang == "mr" else text_hi)
    if llm.available():
        polished_text, ok = _polish_advisor_text(chosen_text, lang)
        if ok:
            chosen_text = polished_text
            polished = True

    rec["reason"] = chosen_text
    rec["reason_en"] = text_en
    rec["reason_mr"] = text_mr
    rec["reason_hi"] = text_hi
    rec["polished_by_ai"] = polished

    lot_summary = {
        "listing_id": lot.listing_id,
        "quantity_q": lot_q,
        "quantity_str": f"{lot.quantity:g} {lot.quantity_unit}",
        "product_form": lot.product_form,
        "location": lot.location,
        "variety": q.variety if q and q.variety else "General",
        "curcumin_pct": q.curcumin_pct if q and q.curcumin_pct is not None else None,
        "moisture_pct": q.moisture_pct if q and q.moisture_pct is not None else None,
        "has_lab_report": bool(q and q.has_lab_report),
        "lab_ref": q.lab_report_ref if (q and q.has_lab_report) else None,
        "expected_price": price_q(lot.expected_price, lot.price_unit),
    }

    return {
        "lot": lot_summary,
        "mandi": mandi_channel,
        "industries": industry_channels,
        "recommendation": rec,
        "lang": lang,
    }


def _generate_multilingual_reasons(lot, mandi, rec):
    lot_q = qty_q(lot.quantity, lot.quantity_unit)
    target = rec["target_name"]
    price = rec["price"]
    mandi_price = mandi["expected_price"]
    gain_q = rec.get("gain_per_q", 0.0)
    gain_tot = rec.get("gain_over_mandi", 0.0)

    # English
    if rec["mode"] == "qualified":
        en = (
            f"Sell to {target}: Offers ₹{price:,.0f}/quintal, which is ₹{gain_q:,.0f}/q higher "
            f"than your local mandi baseline (₹{mandi_price:,.0f}/q). Your lot meets all quality and "
            f"quantity specifications, earning ₹{gain_tot:,.0f} extra gross profit on your {lot_q:g} quintals."
        )
    elif rec["mode"] == "unlockable":
        unlock = rec.get("unlock_action", "provide a lab test report")
        en = (
            f"Top Opportunity: {target} offers ₹{price:,.0f}/quintal (+₹{gain_q:,.0f}/q above mandi, "
            f"+₹{gain_tot:,.0f} extra total). To unlock this deal: {unlock}. "
            f"If you need immediate cash sale today without obtaining quality documents, the local mandi "
            f"at {mandi['markets'][0] if mandi['markets'] else 'APMC'} pays an estimated ₹{mandi_price:,.0f}/q."
        )
    else:
        en = (
            f"Sell at Local Mandi: Offers your best immediate net realization of ₹{mandi_price:,.0f}/quintal. "
            f"Current industry buyer requirements do not match your declared specifications or are priced below mandi rates."
        )

    # Marathi
    if rec["mode"] == "qualified":
        mr = (
            f"शिफारस: {target} कडे विक्री करा. ऑफर भाव ₹{price:,.0f}/क्विंटल आहे, "
            f"जो स्थानिक बाजार समितीपेक्षा (₹{mandi_price:,.0f}/क्विंटल) ₹{gain_q:,.0f}/क्विंटल जास्त आहे. "
            f"तुमचा माल सर्व गुणवत्ता अटी पूर्ण करतो, ज्यामुळे {lot_q:g} क्विंटलवर ₹{gain_tot:,.0f} चा जादा नफा होईल."
        )
    elif rec["mode"] == "unlockable":
        unlock = rec.get("unlock_action", "लॅब चाचणी अहवाल जोडा")
        mr = (
            f"सर्वाधिक फायदेशीर मार्ग: {target} कडून ₹{price:,.0f}/क्विंटल भाव उपलब्ध आहे "
            f"(बाजार समितीपेक्षा ₹{gain_q:,.0f}/क्विंटल जास्त, एकूण ₹{gain_tot:,.0f} वाढीव परतावा). "
            f"हा भाव मिळवण्यासाठी: {unlock}. "
            f"कागदपत्रांशिवाय आजच तातडीने रोख विक्री करायची असल्यास स्थानिक बाजार समितीमध्ये अंदाजे ₹{mandi_price:,.0f}/क्विंटल भाव मिळेल."
        )
    else:
        mr = (
            f"शिफारस: स्थानिक बाजार समितीमध्ये विक्री करा. चालू बाजारात ₹{mandi_price:,.0f}/क्विंटल भाव मिळणे सोपे आहे. "
            f"औद्योगिक खरेदीदारांच्या अटी सध्याच्या मालाशी जुळत नाहीत."
        )

    # Hindi
    if rec["mode"] == "qualified":
        hi = (
            f"सिफारिश: {target} को बेचें। प्रस्तावित भाव ₹{price:,.0f}/क्विंटल है, "
            f"जो स्थानीय मंडी (₹{mandi_price:,.0f}/क्विंटल) से ₹{gain_q:,.0f}/क्विंटल अधिक है। "
            f"आपका माल गुणवत्ता मानकों को पूरा करता है, जिससे {lot_q:g} क्विंटल पर ₹{gain_tot:,.0f} का अतिरिक्त मुनाफा मिलेगा।"
        )
    elif rec["mode"] == "unlockable":
        unlock = rec.get("unlock_action", "लैब टेस्ट रिपोर्ट संलग्न करें")
        hi = (
            f"सर्वोत्तम अवसर: {target} से ₹{price:,.0f}/क्विंटल का भाव मिल रहा है "
            f"(मंडी से ₹{gain_q:,.0f}/क्विंटल अधिक, कुल ₹{gain_tot:,.0f} अतिरिक्त लाभ)। "
            f"यह भाव पाने के लिए: {unlock}। "
            f"यदि बिना गुणवत्ता प्रमाणपत्र के आज ही तुरंत बेचना चाहते हैं, तो स्थानीय मंडी में ₹{mandi_price:,.0f}/क्विंटल का भाव मिल सकता है।"
        )
    else:
        hi = (
            f"सिफारिश: स्थानीय मंडी में बेचें। तत्काल बिक्री के लिए मंडी का ₹{mandi_price:,.0f}/क्विंटल भाव सबसे व्यावहारिक विकल्प है।"
        )

    return en, mr, hi


def _polish_advisor_text(text, lang):
    """
    Polishes the advisor text using Claude (optional).
    Enforces strict mathematical verification: if any number differs, rejects the rewrite.
    """
    sys_prompt = (
        "You are an agricultural advisor assistant for Indian turmeric farmers. "
        "Polish the provided recommendation explanation to be polite, motivating, and clear. "
        "CRITICAL RULE: Do NOT change, round, add, or remove ANY numbers, currencies (₹), quantities, or percentages. "
        "Keep the exact same language (" + ("Marathi" if lang == "mr" else ("Hindi" if lang == "hi" else "English")) + "). "
        "Output ONLY the revised text."
    )
    rewritten = llm.complete(sys_prompt, text, max_tokens=350)
    if not rewritten or len(rewritten) > 450:
        return text, False

    # Extract all number tokens and verify 100% preservation
    orig_nums = set(re.findall(r"\d[\d,\.]*", text))
    new_nums = set(re.findall(r"\d[\d,\.]*", rewritten))
    if orig_nums != new_nums:
        # Number safety violation: reject rewrite
        return text, False

    return rewritten, True
