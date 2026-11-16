"""
Turmeric Market Recommendation Agent
=====================================
Analyses stored REAL mandi price records (from data.gov.in / Agmarknet) and
recommends the best market(s) for a farmer based on:
  - Farmer's location (district / state text matching against actual DB values)
  - Turmeric variety (matched against actual variety values in the records)
  - Quantity (quintals)
  - Optional transport cost per quintal (entered by the farmer)

DATA HONESTY RULES (strictly enforced):
  - SAMPLE DATA rows are NEVER used in any calculation or recommendation.
  - If only sample data is present, the agent returns an error — no fake recommendations.
  - All prices shown come from actual stored Agmarknet / data.gov.in records.
  - Gross value  = actual modal price x quantity_q                    (exact arithmetic)
  - Net value    = (actual modal price - transport_cost_q) x qty_q   (only if farmer provided cost)
  - Price trend  = least-squares regression on stored daily averages  (not a forecast)
  - No claim of a trained ML model unless one is genuinely implemented.

Functions
---------
  recommend(location, variety, quantity_q, transport_cost_q)
      -> dict: ranked_markets, best, summary_text, warnings, errors, …

  data_collection_agent()
      -> validation summary of stored real price records

  comparison_summary(state=None)
      -> comparison table for the latest real data date
"""

import re
from datetime import date
from statistics import mean, median, pstdev

from sqlalchemy import func

from models import MarketPrice, db

STALE_DAYS = 7        # records older than this are labelled "Historical"
WINDOW_DAYS = 30      # rolling window for trend / volatility
MIN_TREND_DATES = 5   # minimum distinct date-points required before showing a trend

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _real_turmeric():
    """
    Return only REAL (non-sample) turmeric MarketPrice rows with a modal price and date.
    SAMPLE DATA rows are never included in any calculation.
    """
    return MarketPrice.query.filter(
        func.lower(MarketPrice.commodity).like("%turmeric%"),
        MarketPrice.modal_price.isnot(None),
        MarketPrice.reporting_date.isnot(None),
        ~MarketPrice.source_name.like("SAMPLE%"),   # exclude sample rows
    ).all()


def _has_any_data():
    """Returns True when at least one real turmeric row exists."""
    return MarketPrice.query.filter(
        func.lower(MarketPrice.commodity).like("%turmeric%"),
        ~MarketPrice.source_name.like("SAMPLE%"),
    ).count() > 0


def _has_only_sample():
    """Returns True when DB has sample rows but no real rows."""
    sample_count = MarketPrice.query.filter(
        func.lower(MarketPrice.commodity).like("%turmeric%"),
        MarketPrice.source_name.like("SAMPLE%"),
    ).count()
    real_count = MarketPrice.query.filter(
        func.lower(MarketPrice.commodity).like("%turmeric%"),
        ~MarketPrice.source_name.like("SAMPLE%"),
    ).count()
    return sample_count > 0 and real_count == 0


_STOP = {"district", "taluka", "dist", "india", "market", "apmc",
         "the", "and", "near", "tal", "state", "village"}

# Known district-to-state mapping for intelligent regional fallbacks
DISTRICT_TO_STATE = {
    # Maharashtra
    "sangli": "Maharashtra", "satara": "Maharashtra", "kolhapur": "Maharashtra",
    "solapur": "Maharashtra", "pune": "Maharashtra", "ahmednagar": "Maharashtra",
    "hingoli": "Maharashtra", "nanded": "Maharashtra", "parbhani": "Maharashtra",
    "latur": "Maharashtra", "osmanabad": "Maharashtra", "dharashiv": "Maharashtra",
    "aurangabad": "Maharashtra", "chhatrapati sambhajinagar": "Maharashtra",
    "jalna": "Maharashtra", "beed": "Maharashtra", "nashik": "Maharashtra",
    "jalgaon": "Maharashtra", "dhule": "Maharashtra", "nandurbar": "Maharashtra",
    "buldhana": "Maharashtra", "akola": "Maharashtra", "washim": "Maharashtra",
    "amravati": "Maharashtra", "yavatmal": "Maharashtra", "wardha": "Maharashtra",
    "nagpur": "Maharashtra", "bhandara": "Maharashtra", "gondia": "Maharashtra",
    "chandrapur": "Maharashtra", "gadchiroli": "Maharashtra", "thane": "Maharashtra",
    "palghar": "Maharashtra", "raigad": "Maharashtra", "ratnagiri": "Maharashtra",
    "sindhudurg": "Maharashtra",
    # Telangana
    "nizamabad": "Telangana", "adilabad": "Telangana", "karimnagar": "Telangana",
    "warangal": "Telangana", "khammam": "Telangana", "hyderabad": "Telangana",
    "jagtial": "Telangana", "kamareddy": "Telangana", "nirmal": "Telangana",
    # Tamil Nadu
    "erode": "Tamil Nadu", "salem": "Tamil Nadu", "coimbatore": "Tamil Nadu",
    "dharmapuri": "Tamil Nadu", "namakkal": "Tamil Nadu", "tiruppur": "Tamil Nadu",
    # Andhra Pradesh
    "guntur": "Andhra Pradesh", "krishna": "Andhra Pradesh", "kurnool": "Andhra Pradesh",
    "kadapa": "Andhra Pradesh", "chittoor": "Andhra Pradesh", "prakasam": "Andhra Pradesh",
    "duggirala": "Andhra Pradesh",
    # Karnataka
    "chamarajanagar": "Karnataka", "mysore": "Karnataka", "belagavi": "Karnataka",
    "bagalkot": "Karnataka", "bidar": "Karnataka",
}


def _tokens(text):
    """Lower-case 3+ char word tokens, excluding noise words."""
    return {w for w in re.findall(r"[a-z]{3,}", (text or "").lower()) if w not in _STOP}


def _infer_state(location_text, loc_tokens):
    """Infer state name dynamically from user input, database records, or regional mapping."""
    loc_lc = (location_text or "").lower()

    # 1. Direct state name match in location text
    known_states = ("Maharashtra", "Telangana", "Tamil Nadu", "Andhra Pradesh", "Karnataka",
                    "Kerala", "Odisha", "Assam", "Meghalaya", "West Bengal", "Gujarat",
                    "Madhya Pradesh", "Uttar Pradesh", "Bihar")
    for st in known_states:
        if st.lower() in loc_lc:
            return st

    # 2. Dynamic database lookup: match user location against all stored district-state pairs
    try:
        db_pairs = MarketPrice.query.filter(
            MarketPrice.district.isnot(None),
            MarketPrice.state.isnot(None),
            ~MarketPrice.source_name.like("SAMPLE%")
        ).with_entities(MarketPrice.district, MarketPrice.state).distinct().all()
        for d, s in db_pairs:
            if d and s and (d.lower() in loc_lc or d.lower() in loc_tokens):
                return s
    except Exception:
        pass

    # 3. Known dictionary fallback
    for dist, st in DISTRICT_TO_STATE.items():
        if dist in loc_lc or dist in loc_tokens:
            return st
    return None


def _location_match_score(row, loc_tokens, inferred_state=None):
    """
    Returns a score for how well a market row matches the farmer's location tokens.
      3 = district or market name matches (strongest — farmer's local market/catchment)
      1 = state matches (farmer's state or inferred state)
      0 = no match
    """
    if not loc_tokens and not inferred_state:
        return 0
    score = 0
    if loc_tokens & _tokens(row.district or ""):
        score += 3
    if loc_tokens & _tokens(row.market_name or ""):
        score += 3
    if (loc_tokens & _tokens(row.state or "")) or (inferred_state and (row.state or "").lower() == inferred_state.lower()):
        score = max(score, 1)
    return score


def _linreg(xs, ys):
    """Least-squares slope and R². Returns (slope, r2) or None."""
    if len(xs) < 2:
        return None
    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    tot = sum((y - my) ** 2 for y in ys)
    res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    return b, (1 - res / tot) if tot else 0.0


# ---------------------------------------------------------------------------
# Agent 1: Data Collection & Validation
# ---------------------------------------------------------------------------

def data_collection_agent():
    """
    Inspects and validates stored REAL mandi price records.
    Returns a status dict — always honest about data quality and recency.
    """
    only_sample = _has_only_sample()
    rows = _real_turmeric()

    if not rows:
        if only_sample:
            status = (
                "The database currently contains only SAMPLE (invented demo) price rows — "
                "no real Agmarknet data has been imported. "
                "Ask your admin to click 'Sync now' (requires DATA_GOV_API_KEY in .env) "
                "or import a CSV file downloaded from data.gov.in."
            )
        else:
            status = (
                "No mandi price records found. "
                "Ask your admin to run 'Sync now' (Admin dashboard) after configuring DATA_GOV_API_KEY in .env, "
                "or import a CSV from data.gov.in."
            )
        return {
            "total_records": 0, "latest_date": None, "age_days": None,
            "is_stale": True, "only_sample": only_sample,
            "states_covered": [], "markets_covered": [], "varieties_covered": [],
            "source_names": [], "missing_fields_pct": 100, "status_text": status,
        }

    latest = max(r.reporting_date for r in rows)
    age = (date.today() - latest).days
    is_stale = age > STALE_DAYS

    missing = sum(1 for r in rows if not r.state or not r.district)
    missing_pct = round(100 * missing / len(rows), 1)

    states   = sorted({r.state        for r in rows if r.state})
    markets  = sorted({r.market_name  for r in rows if r.market_name})
    varieties = sorted({r.variety     for r in rows if r.variety})
    sources  = sorted({r.source_name  for r in rows if r.source_name})

    if is_stale:
        status = (
            f"Real Agmarknet data is present but the newest record is {age} days old "
            f"({latest:%d %b %Y}). Prices may not reflect today's market. "
            "Ask your admin to sync again."
        )
    else:
        status = (
            f"Real Agmarknet data is current. Latest record: {latest:%d %b %Y} ({age} day(s) old). "
            f"Source: {'; '.join(sources[:2])}."
        )

    return {
        "total_records": len(rows), "latest_date": latest, "age_days": age,
        "is_stale": is_stale, "only_sample": False,
        "states_covered": states, "markets_covered": markets,
        "varieties_covered": varieties, "source_names": sources,
        "missing_fields_pct": missing_pct, "status_text": status,
    }


# ---------------------------------------------------------------------------
# Agent 2: Market Price Analysis & Comparison
# ---------------------------------------------------------------------------

def comparison_summary(state=None):
    """
    Comparison table of REAL markets for the latest data date.
    Returns [] when no real data.
    """
    rows = _real_turmeric()
    if not rows:
        return []
    latest = max(r.reporting_date for r in rows)
    latest_rows = [r for r in rows if r.reporting_date == latest]
    if state:
        state_lc = state.strip().lower()
        latest_rows = [r for r in latest_rows if (r.state or "").lower() == state_lc]

    out = []
    for r in sorted(latest_rows, key=lambda x: -(x.modal_price or 0)):
        out.append({
            "market_name":    r.market_name,
            "state":          r.state or "—",
            "district":       r.district or "—",
            "variety":        r.variety or "—",
            "modal_price":    r.modal_price,
            "min_price":      r.minimum_price,
            "max_price":      r.maximum_price,
            "reporting_date": r.reporting_date,
            "source_name":    r.source_name or "Unknown",
            "is_stale":       (date.today() - r.reporting_date).days > STALE_DAYS,
        })
    return out


# ---------------------------------------------------------------------------
# Agent 3: Farmer Market Recommendation
# ---------------------------------------------------------------------------

def recommend(location, variety, quantity_q, transport_cost_q=None):
    """
    Recommend the best market(s) for a farmer to sell turmeric.

    Parameters
    ----------
    location        : str   farmer's district / village
    variety         : str   turmeric variety (blank = any variety)
    quantity_q      : float quantity in quintals
    transport_cost_q: float optional farmer-supplied transport cost (Rs/quintal)

    Returns
    -------
    dict:
      errors          list — input validation errors (empty on success)
      ranked_markets  list of dicts for each market (best first, max 10)
      best            top market dict, or None
      summary_text    plain English summary
      data_date       date object of latest data used
      is_stale        bool
      data_warning    str or None
      variety_warning str or None
      no_local        bool — True when no district/market match found for the location
      local_scope     str — describes what "local" meant in this search
    """
    # --- Input validation ---
    errors = []
    if not location or len(location.strip()) < 2:
        errors.append("Please enter your location (district or village name).")
    if quantity_q is None or quantity_q <= 0:
        errors.append("Quantity must be greater than 0.")
    if quantity_q and quantity_q > 100_000:
        errors.append("Quantity seems very large. Please enter in quintals (1 tonne = 10 quintals).")
    if errors:
        return _empty_result(errors=errors)

    # --- Block sample-only data ---
    if _has_only_sample():
        return _empty_result(errors=[
            "The database contains only SAMPLE (invented demo) prices — no real Agmarknet data. "
            "Real market data must be imported before recommendations can be generated. "
            "Ask your admin to configure DATA_GOV_API_KEY and click 'Sync now'."
        ])

    rows = _real_turmeric()
    if not rows:
        return _empty_result(errors=[
            "No real mandi price records found in the database. "
            "Ask your admin to import data from data.gov.in (Admin → Sync now)."
        ])

    latest = max(r.reporting_date for r in rows)
    age = (date.today() - latest).days
    is_stale = age > STALE_DAYS

    # --- Step 1: Recent candidates (last WINDOW_DAYS from latest date in DB) ---
    window = [r for r in rows if (latest - r.reporting_date).days <= WINDOW_DAYS]
    # One latest record per (market, variety) pair
    latest_per = {}
    for r in sorted(window, key=lambda x: x.reporting_date):
        latest_per[(r.market_name, r.variety or "")] = r
    candidates = list(latest_per.values())

    # --- Step 2: Variety filter ---
    variety_warning = None
    if variety and variety.strip():
        v_lc = variety.strip().lower()
        variety_matched = [
            r for r in candidates
            if (r.variety or "").strip().lower() == v_lc
        ]
        if variety_matched:
            candidates = variety_matched
        else:
            # Check partial match (e.g. "finger" matches "Dry Finger")
            variety_partial = [
                r for r in candidates
                if v_lc in (r.variety or "").strip().lower()
                or (r.variety or "").strip().lower() in v_lc
            ]
            if variety_partial:
                variety_warning = (
                    f"No exact match for variety '{variety}'. "
                    f"Showing {len(variety_partial)} record(s) with a partial variety match. "
                    f"Actual variety values in data: {', '.join(sorted({r.variety for r in variety_partial if r.variety}))}."
                )
                candidates = variety_partial
            else:
                variety_warning = (
                    f"Variety '{variety}' not found in the last {WINDOW_DAYS} days of records. "
                    f"Available varieties: {', '.join(sorted({r.variety for r in candidates if r.variety}) or ['(none recorded)'])}. "
                    "Showing recommendations for all varieties."
                )

    # --- Step 3: Location matching (scored, not boolean) ---
    loc_tokens = _tokens(location)
    inferred_state = _infer_state(location, loc_tokens)

    # Score every candidate
    scored_candidates = [(r, _location_match_score(r, loc_tokens, inferred_state)) for r in candidates]

    # Separate: district/market match (score >= 2) vs state-only match (score 1) vs no match (score 0)
    district_local = [r for r, s in scored_candidates if s >= 2]   # district or market name match
    state_local    = [r for r, s in scored_candidates if s == 1]   # state name match only
    no_match       = [r for r, s in scored_candidates if s == 0]

    # Decide which pool to use, and explain honestly
    if district_local:
        used_rows = district_local
        no_local = False
        local_scope = (
            f"Markets matching your local district/market '{location}' "
            f"({len(district_local)} record(s) found)."
        )
    elif state_local:
        used_rows = state_local
        no_local = False
        state_name = inferred_state or (state_local[0].state if state_local else "your state")
        local_scope = (
            f"No direct market records found for district/town '{location}'. "
            f"Showing nearby {state_name} markets ({len(state_local)} record(s)). "
            "Factor in transport cost — these may be some distance from your farm."
        )
    else:
        used_rows = candidates
        no_local = True
        local_scope = (
            f"No local or state-level match found for '{location}' in the current data. "
            f"Showing all {len(candidates)} available markets nationally. "
            "These may be far from you — always factor in your actual transport cost."
        )

    # --- Step 4: Trend per market (using all window rows, regardless of variety) ---
    trend_by_market = {}
    for r in window:
        trend_by_market.setdefault(r.market_name, []).append(r)

    def _market_trend(market_name):
        mrows = trend_by_market.get(market_name, [])
        by_day = {}
        for r in mrows:
            by_day.setdefault(r.reporting_date, []).append(r.modal_price)
        days = sorted(by_day)
        if len(days) < MIN_TREND_DATES:
            return None, None, None
        ys = [mean(by_day[d]) for d in days]
        xs = [(d - days[0]).days for d in days]
        fit = _linreg(xs, ys)
        if not fit:
            return None, None, None
        slope, r2 = fit
        vol = pstdev(ys) if len(ys) > 1 else 0
        return slope, r2, vol

    # --- Step 5: Score and rank ---
    transport_q = transport_cost_q if (transport_cost_q is not None and transport_cost_q >= 0) else None

    scored = []
    for r in used_rows:
        if not r.modal_price:
            continue
        gross = r.modal_price * quantity_q
        net   = (r.modal_price - transport_q) * quantity_q if transport_q is not None else None

        slope, r2, vol = _market_trend(r.market_name)
        loc_score = _location_match_score(r, loc_tokens, inferred_state)
        rec_age = (latest - r.reporting_date).days

        # Ranking score: modal price (primary) + locality bonus + rising trend bonus
        rank_score = r.modal_price
        rank_score += r.modal_price * 0.03 * min(loc_score, 3) / 3  # up to +3% for close match
        if slope and slope > 5 and r2 and r2 > 0.4:
            rank_score += r.modal_price * 0.01   # +1% for confirmed rising trend
        if rec_age == 0:
            rank_score += r.modal_price * 0.005  # +0.5% for same-day data

        # Trend direction label
        if slope is not None:
            trend_dir = "rising" if slope > 5 else ("falling" if slope < -5 else "stable")
        else:
            trend_dir = None

        # Plain-language explanation — every claim cites source and date
        lines = [
            f"Modal price ₹{r.modal_price:,.0f}/quintal "
            f"(source: {r.source_name or 'Agmarknet'}, date: {r.reporting_date:%d %b %Y}).",
        ]
        if r.minimum_price and r.maximum_price:
            lines.append(
                f"Price range on that date: ₹{r.minimum_price:,.0f}–₹{r.maximum_price:,.0f}/quintal."
            )
        if loc_score >= 2:
            lines.append(
                f"District/market match for your location '{location}' — lower transport distance expected."
            )
        elif loc_score == 1:
            lines.append(
                f"State-level match for '{location}'. This market is in the same state "
                "but may not be your nearest mandi — confirm distance before selling."
            )
        else:
            lines.append(
                f"No geographic match for '{location}'. "
                "Verify distance and factor in your actual transport cost."
            )
        if transport_q is not None and transport_q > 0:
            net_price = r.modal_price - transport_q
            lines.append(
                f"Estimated net price after transport ₹{transport_q:,.0f}/q: "
                f"₹{net_price:,.0f}/quintal."
            )
        if trend_dir == "rising":
            lines.append(
                f"Trend (last {WINDOW_DAYS} days): rising (~+₹{slope:.0f}/day, R²={r2:.2f}). "
                "This is a linear trend, not a price forecast."
            )
        elif trend_dir == "falling":
            lines.append(
                f"Trend (last {WINDOW_DAYS} days): falling (~{slope:.0f}/day, R²={r2:.2f}). "
                "Consider selling sooner. This is a trend, not a guarantee."
            )
        elif trend_dir == "stable":
            lines.append(
                f"Trend (last {WINDOW_DAYS} days): broadly stable. "
                "This is a linear trend, not a price forecast."
            )
        else:
            lines.append(
                f"Fewer than {MIN_TREND_DATES} date-points available — trend not shown."
            )
        if vol and vol > 0:
            vol_label = "low" if vol < 200 else ("moderate" if vol < 500 else "high")
            lines.append(f"Price volatility (std dev): ₹{vol:,.0f}/quintal — {vol_label}.")
        if rec_age > STALE_DAYS:
            lines.append(
                f"Note: this record is {rec_age} days old (historical). "
                "Verify the current price at the mandi."
            )

        scored.append({
            "market_name":      r.market_name,
            "state":            r.state or "—",
            "district":         r.district or "—",
            "variety":          r.variety or "—",
            "modal_price":      r.modal_price,
            "min_price":        r.minimum_price,
            "max_price":        r.maximum_price,
            "reporting_date":   r.reporting_date,
            "source_name":      r.source_name or "Unknown",
            "is_local":         loc_score >= 2,
            "loc_score":        loc_score,
            "is_stale":         rec_age > STALE_DAYS,
            "gross_value":      round(gross, 2),
            "net_value":        round(net, 2) if net is not None else None,
            "trend_slope":      round(slope, 2) if slope is not None else None,
            "trend_direction":  trend_dir,
            "trend_r2":         round(r2, 3) if r2 is not None else None,
            "volatility":       round(vol, 0) if vol else None,
            "score":            round(rank_score, 2),
            "explanation":      " ".join(lines),
        })

    scored.sort(key=lambda x: -x["score"])

    # --- Step 6: Data warning ---
    data_warning = None
    if is_stale:
        data_warning = (
            f"Data is {age} days old (latest record: {latest:%d %b %Y}). "
            "These are historical prices, not today's rates. "
            "Verify the current price at your mandi before selling."
        )

    # --- Step 7: Summary text ---
    if scored:
        best = scored[0]
        parts = [
            f"Based on {len(used_rows)} real Agmarknet record(s) from the last {WINDOW_DAYS} days",
            f"({'your district/area' if not no_local else 'all markets — no local data found'}),"
            f" the highest modal price is at {best['market_name']} ({best['state']})"
            f" at \u20b9{best['modal_price']:,.0f}/quintal",
            f"(data: {best['reporting_date']:%d %b %Y}, source: {best['source_name']}).",
        ]
        if quantity_q:
            parts.append(
                f"Estimated gross value for {quantity_q:g} quintal(s): "
                f"\u20b9{best['gross_value']:,.0f}."
            )
        if transport_q is not None and transport_q > 0 and best["net_value"] is not None:
            parts.append(
                f"After transport cost \u20b9{transport_q:,.0f}/q, estimated net: "
                f"\u20b9{best['net_value']:,.0f}."
            )
        if best["trend_direction"] == "falling":
            parts.append(
                "Note: price trend at this market is falling — compare with other markets below."
            )
        parts.append(
            "These estimates use actual mandi records. Confirm today's rate at the mandi before selling."
        )
        summary_text = " ".join(parts)
    else:
        summary_text = "No recommendations could be generated from the available real data."

    return {
        "errors":          [],
        "ranked_markets":  scored[:10],
        "best":            scored[0] if scored else None,
        "summary_text":    summary_text,
        "data_date":       latest,
        "is_stale":        is_stale,
        "data_warning":    data_warning,
        "variety_warning": variety_warning,
        "no_local":        no_local,
        "local_scope":     local_scope,
    }


def _empty_result(errors=None):
    return {
        "errors":          errors or [],
        "ranked_markets":  [],
        "best":            None,
        "summary_text":    None,
        "data_date":       None,
        "is_stale":        True,
        "data_warning":    None,
        "variety_warning": None,
        "no_local":        True,
        "local_scope":     "",
    }
