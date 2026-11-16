"""
Industry Price Agent
====================
Analyzes buyer demand records on HaldiSetu across the four industry sectors:
  1. Food & spice company
  2. Medicine / nutraceutical maker
  3. Cosmetics / natural-dye maker
  4. Research lab / extract maker

For each industry, it calculates:
  - Offer range (min, max, average) and spread vs current mandi baseline price
  - Stated buyer requirements (typical curcumin %, moisture %, lab report requirements)
  - Data confidence flag (low/medium/high, test-buyer disclosure)

All calculations are deterministic and auditable directly from stored BuyerDemand records.
"""
from statistics import mean
from sqlalchemy import func

from matching import price_q
from models_market import BuyerDemand, INDUSTRIES
from price_engine import mandi_baseline


INDUSTRY_METADATA = {
    "Food & spice company": {
        "display_name": "Food & Spice Processing",
        "short_name": "Food & Spice",
        "description": "Ground spices, packaged turmeric, food formulations, oleoresin standard.",
        "icon": "🍲",
    },
    "Medicine / nutraceutical maker": {
        "display_name": "Medicine & Nutraceuticals",
        "short_name": "Medicine",
        "description": "Ayurvedic medicines, supplements, pharmaceutical extract formulations.",
        "icon": "💊",
    },
    "Cosmetics / natural-dye maker": {
        "display_name": "Cosmetics & Natural Dye",
        "short_name": "Cosmetics",
        "description": "Skincare, cosmetics formulations, natural textile/food dyes.",
        "icon": "🌿",
    },
    "Research lab / extract maker": {
        "display_name": "Research Lab & Extract Maker",
        "short_name": "Research / Extract",
        "description": "High-purity curcumin extraction (95%), HPLC laboratory standards.",
        "icon": "🔬",
    },
}


def analyze_industry(industry_name, mandi_base_price=None):
    """
    Analyzes one industry sector from stored BuyerDemand records.
    Returns a structured dictionary of price stats, requirements, and confidence.
    """
    demands = BuyerDemand.query.filter_by(industry_type=industry_name, status="open").all()
    meta = INDUSTRY_METADATA.get(industry_name, {
        "display_name": industry_name,
        "short_name": industry_name,
        "description": "",
        "icon": "🏢",
    })

    if not demands:
        return {
            "industry": industry_name,
            "display_name": meta["display_name"],
            "short_name": meta["short_name"],
            "description": meta["description"],
            "icon": meta["icon"],
            "n_offers": 0,
            "min_price": None,
            "max_price": None,
            "avg_price": None,
            "mandi_baseline": mandi_base_price,
            "spread_vs_mandi": None,
            "requirements": {
                "curcumin_min_typical": None,
                "moisture_max_typical": None,
                "lab_required_count": 0,
                "lab_required_pct": 0.0,
                "forms_accepted": [],
            },
            "confidence": {
                "level": "none",
                "badge": "No active offers",
                "badge_class": "grey",
                "is_demo_only": False,
                "real_count": 0,
                "demo_count": 0,
                "reason": "No buyers have posted open requirements in this sector yet.",
            },
            "demands": [],
        }

    prices = [price_q(d.offered_price, d.price_unit) for d in demands]
    min_p = min(prices)
    max_p = max(prices)
    avg_p = mean(prices)

    # Spread vs Mandi Baseline
    spread = None
    if mandi_base_price and mandi_base_price > 0:
        diff = avg_p - mandi_base_price
        diff_pct = (diff / mandi_base_price) * 100
        direction = "above" if diff > 10 else ("below" if diff < -10 else "at par")
        sign = "+" if diff > 0 else ""
        spread = {
            "diff": diff,
            "diff_pct": diff_pct,
            "direction": direction,
            "label": f"{sign}₹{diff:,.0f}/q ({sign}{diff_pct:.1f}%) {direction} mandi",
            "css_class": "ok" if diff > 0 else ("err" if diff < 0 else "grey"),
        }

    # Requirements synthesis from buyer demand posts
    curcumins = [d.min_curcumin for d in demands if d.min_curcumin is not None]
    moistures = [d.max_moisture for d in demands if d.max_moisture is not None]
    lab_count = sum(1 for d in demands if d.requires_lab_report)
    forms = sorted({d.product_form for d in demands if d.product_form})

    reqs = {
        "curcumin_min_typical": min(curcumins) if curcumins else None,
        "curcumin_range": (min(curcumins), max(curcumins)) if curcumins else None,
        "moisture_max_typical": max(moistures) if moistures else None,
        "moisture_range": (min(moistures), max(moistures)) if moistures else None,
        "lab_required_count": lab_count,
        "lab_required_pct": (lab_count / len(demands)) * 100,
        "forms_accepted": forms,
    }

    # Confidence & Test-Buyer Flagging
    demo_count = sum(1 for d in demands if d.is_demo)
    real_count = len(demands) - demo_count
    is_demo_only = (demo_count == len(demands))

    if is_demo_only:
        conf_level = "test"
        badge = f"{demo_count} test buyer{'s' if demo_count > 1 else ''}"
        badge_class = "warn"
        reason = (
            f"All {demo_count} requirement(s) are from clearly labelled test buyers for demonstration. "
            "Real rates will appear once commercial industry buyers register on HaldiSetu."
        )
    elif real_count < 3:
        conf_level = "low"
        badge = f"{real_count} verified offer{'s' if real_count > 1 else ''}"
        badge_class = "info"
        reason = f"Low confidence: only {real_count} verified buyer offer(s) recorded."
    else:
        conf_level = "high"
        badge = f"{real_count} verified offers"
        badge_class = "ok"
        reason = f"High confidence: {real_count} commercial buyer offers available."

    return {
        "industry": industry_name,
        "display_name": meta["display_name"],
        "short_name": meta["short_name"],
        "description": meta["description"],
        "icon": meta["icon"],
        "n_offers": len(demands),
        "min_price": min_p,
        "max_price": max_p,
        "avg_price": avg_p,
        "mandi_baseline": mandi_base_price,
        "spread_vs_mandi": spread,
        "requirements": reqs,
        "confidence": {
            "level": conf_level,
            "badge": badge,
            "badge_class": badge_class,
            "is_demo_only": is_demo_only,
            "real_count": real_count,
            "demo_count": demo_count,
            "reason": reason,
        },
        "demands": demands,
    }


def get_all_industry_stats(lot=None, location=None):
    """
    Returns analysis for all 4 industry categories compared with the local or national mandi baseline.
    """
    base_mandi = None
    if lot:
        base = mandi_baseline(lot)
        if base and base.get("modal"):
            base_mandi = base["modal"]
    elif location:
        from price_engine import baseline_for_location
        base = baseline_for_location(location)
        if base and base.get("modal"):
            base_mandi = base["modal"]
    else:
        from price_engine import _rows
        rows = _rows()
        if rows:
            base_mandi = mean([r.modal_price for r in rows if r.modal_price])

    results = []
    for ind in INDUSTRIES:
        results.append(analyze_industry(ind, base_mandi))
    return results


def refresh_industry_stats():
    """
    Orchestration hook: calculates current industry stats and returns a summary for logging/auditing.
    """
    stats = get_all_industry_stats()
    summary = []
    for s in stats:
        summary.append({
            "industry": s["industry"],
            "offers": s["n_offers"],
            "avg_price": round(s["avg_price"]) if s["avg_price"] else None,
            "is_demo_only": s["confidence"]["is_demo_only"],
        })
    return summary
