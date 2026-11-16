"""
Agent endpoints (blueprint "ag"):
  POST /lots/intake                       lot intake agent  (text/voice -> form fields + questions)
  GET  /lots/<lid>/negotiate/<did>        negotiation agent (counter-offer + message draft; farmer approves & sends)
  POST /market/alerts, .../<id>/delete    farmer price alerts          POST /notifications/read
  POST /market/recommend                  market recommendation agent  (location + variety + qty -> best market)
"""
from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from access import audit, login_required, verified_required
from lot_intake_agent import parse_lot_text
from marketplace import _open_demands, _opt_float, _own_lot
from market_agent import summary
from market_recommend import recommend, data_collection_agent, comparison_summary
from matching import direct_offers, evaluate, rank_demands_for_lot
from models import MarketPrice, db
from models_market import BuyerDemand, Notification, PriceAlert
from negotiation_agent import draft
from price_engine import price_card

bp = Blueprint("ag", __name__)


@bp.route("/lots/intake", methods=["POST"])
@login_required(roles=["farmer"])
def lot_intake():
    text = request.form.get("text", "").strip()
    if len(text) < 3:
        return jsonify({"error": "Describe your lot in a sentence."}), 400
    places = [p[0] for p in db.session.query(MarketPrice.district).distinct()] + \
             [p[0] for p in db.session.query(MarketPrice.market_name).distinct()]
    res = parse_lot_text(text, [p for p in places if p])
    audit("agent_lot_intake", "user", g.user.user_id, f"{res['mode']}: {len(res['fields'])} field(s) understood")
    db.session.commit()
    return jsonify(res)


@bp.route("/lots/<int:lid>/negotiate/<int:did>")
@login_required(roles=["farmer"])
@verified_required
def negotiate(lid, did):
    lot = _own_lot(lid)
    d = db.get_or_404(BuyerDemand, did)
    errs = []
    minimum = _opt_float(request.args.get("min_price"), 0.01, 10_000_000, "Minimum price", errs)
    for e in errs:
        flash(e, "error")
    ranked = rank_demands_for_lot(lot, _open_demands())
    price = price_card(lot, direct_offers(ranked))
    res = draft(lot, d, price, evaluate(lot, d), minimum, request.args.get("lang", "en"))
    audit("agent_negotiation_draft", "demand", did, f"lot {lid}: counter ₹{res['counter']:,.0f}")
    db.session.commit()
    return render_template("negotiate.html", lot=lot, d=d, res=res, ev=evaluate(lot, d),
                           already=any(r.listing_id == lid for r in d.responses))


@bp.route("/where-to-sell")
@bp.route("/lots/<int:lid>/where-to-sell")
@login_required(roles=["farmer"])
def where_to_sell(lid=None):
    """
    Sell-Channel Advisor Agent endpoint:
    Compares local mandi vs 4 industry buyers, recommends the best channel,
    and provides 1-click connect to the negotiation/deal flow.
    """
    from channel_advisor import evaluate_lot_channels
    from industry_agent import get_all_industry_stats
    from models import ProductListing

    farmer_lots = ProductListing.query.filter_by(
        farmer_id=g.user.user_id, listing_status="open"
    ).order_by(ProductListing.created_at.desc()).all()

    if not farmer_lots:
        flash("You have no active lots. Create a lot to use the Sell-Channel Advisor.", "info")
        return redirect(url_for("listing_new"))

    if lid:
        lot = _own_lot(lid)
    else:
        lot = farmer_lots[0]

    lang = request.args.get("lang", "en")
    transport = _opt_float(request.args.get("transport"), 0, 5000, "Transport", [])

    res = evaluate_lot_channels(lot, lang=lang, transport_cost_q=transport)
    ind_stats = get_all_industry_stats(lot=lot)

    audit("agent_sell_channel_advisor", "listing", lot.listing_id,
          f"Recommended {res['recommendation']['target_name']}: ₹{res['recommendation']['price']:,.0f}/q")
    db.session.commit()

    return render_template(
        "where_to_sell.html",
        res=res,
        ind_stats=ind_stats,
        farmer_lots=farmer_lots,
    )


@bp.route("/market/alerts", methods=["POST"])
@login_required(roles=["farmer", "buyer"])
def alert_create():
    errs = []
    thr = _opt_float(request.form.get("threshold_q"), 1, 10_000_000, "Price", errs)
    if thr is None and not errs:
        errs.append("Enter a price.")
    if request.form.get("direction") not in ("above", "below"):
        errs.append("Choose above or below.")
    if PriceAlert.query.filter_by(user_id=g.user.user_id, active=True).count() >= 10:
        errs.append("You can keep at most 10 active alerts.")
    if errs:
        for e in errs:
            flash(e, "error")
    else:
        mk = request.form.get("market_name", "").strip()[:100] or None
        db.session.add(PriceAlert(user_id=g.user.user_id, market_name=mk, direction=request.form["direction"], threshold_q=thr))
        audit("price_alert_created", "user", g.user.user_id, f"{mk or 'highest market'} {request.form['direction']} {thr:g}")
        db.session.commit()
        flash("Alert saved. You will see a notification on your dashboard when a new price record crosses it.", "ok")
    return redirect(url_for("market"))


@bp.route("/market/alerts/<int:aid>/delete", methods=["POST"])
@login_required(roles=["farmer", "buyer"])
def alert_delete(aid):
    a = db.get_or_404(PriceAlert, aid)
    if a.user_id != g.user.user_id:
        abort(403)
    a.active = False
    db.session.commit()
    return redirect(url_for("market"))


@bp.route("/notifications/read", methods=["POST"])
@login_required(roles=["farmer", "buyer"])
def notifications_read():
    Notification.query.filter_by(user_id=g.user.user_id, is_read=False).update({"is_read": True})
    db.session.commit()
    return redirect(url_for("dash.dashboard"))


# ------------------------------------------------------------------ Market Recommendation Agent
@bp.route("/market/recommend", methods=["POST"])
def market_recommend():
    """
    Farmer market recommendation agent.
    Accepts: location, variety, quantity, quantity_unit, transport_cost (all from form POST).
    Returns: renders market.html with recommendation results injected.
    No login required — prices are public. Logged for audit if user is logged in.
    IMPORTANT: Never shows recommendations based on SAMPLE data.
    """
    f = request.form
    errs = []

    location     = f.get("rec_location", "").strip()
    variety      = f.get("rec_variety", "").strip()
    qty_raw      = f.get("rec_quantity", "").strip()
    unit         = f.get("rec_unit", "Quintal")
    transport_raw = f.get("rec_transport", "").strip()

    UNIT_TO_Q = {"Quintal": 1.0, "Kg": 0.01, "Tonne": 10.0}
    qty_q = None
    if qty_raw:
        try:
            qty_q = float(qty_raw) * UNIT_TO_Q.get(unit, 1.0)
        except ValueError:
            errs.append("Quantity must be a number.")

    transport_cost = None
    if transport_raw:
        try:
            transport_cost = float(transport_raw)
            if transport_cost < 0:
                errs.append("Transport cost cannot be negative.")
                transport_cost = None
        except ValueError:
            errs.append("Transport cost must be a number (Rs per quintal).")

    if errs:
        for e in errs:
            flash(e, "error")
        return redirect(url_for("market"))

    result = recommend(location, variety, qty_q, transport_cost)

    if g.user:
        audit(
            "agent_market_recommend", "user", g.user.user_id,
            f"location={location!r} variety={variety!r} qty={qty_q}q "
            f"-> {len(result['ranked_markets'])} market(s) | "
            f"errors={result['errors']}"
        )
        db.session.commit()

    # Re-render the full market page with the recommendation result injected
    from datetime import date as _date
    from sqlalchemy import func
    from auto_refresh import is_due, kick
    from models_market import AuditLog, PriceFlag
    from price_engine import industry_prices, verified_industry_prices
    import flask

    app = flask.current_app
    if is_due(app):
        kick(app)

    base_genuine = MarketPrice.query.filter(
        func.lower(MarketPrice.commodity).like("%turmeric%"),
        ~MarketPrice.source_name.like("SAMPLE%"),
    )

    db_states = [
        s[0] for s in base_genuine.with_entities(MarketPrice.state)
        .filter(MarketPrice.state.isnot(None), MarketPrice.state != "")
        .distinct().order_by(MarketPrice.state).all()
    ]
    districts = [
        d[0] for d in base_genuine.with_entities(MarketPrice.district)
        .filter(MarketPrice.district.isnot(None), MarketPrice.district != "")
        .distinct().order_by(MarketPrice.district).all()
    ]
    markets = [
        m[0] for m in base_genuine.with_entities(MarketPrice.market_name)
        .filter(MarketPrice.market_name.isnot(None), MarketPrice.market_name != "")
        .distinct().order_by(MarketPrice.market_name).all()
    ]
    varieties = [
        v[0] for v in base_genuine.with_entities(MarketPrice.variety)
        .filter(MarketPrice.variety.isnot(None), MarketPrice.variety != "")
        .distinct().order_by(MarketPrice.variety).all()
    ]

    hierarchy = {}
    for st, dt, mk in base_genuine.with_entities(MarketPrice.state, MarketPrice.district, MarketPrice.market_name).distinct().all():
        if not st:
            continue
        hierarchy.setdefault(st, {})
        if dt:
            hierarchy[st].setdefault(dt, [])
            if mk and mk not in hierarchy[st][dt]:
                hierarchy[st][dt].append(mk)

    db_total = base_genuine.count()
    rows = base_genuine.order_by(MarketPrice.reporting_date.desc(), MarketPrice.market_name).limit(50).all()

    pagination = {
        "page": 1, "per_page": "50", "total": db_total,
        "total_pages": max(1, (db_total + 49) // 50),
        "has_prev": False, "has_next": db_total > 50,
        "prev_page": 1, "next_page": 2,
    }

    counts = {
        "match_total": db_total,
        "match_states": len(db_states),
        "match_districts": len(districts),
        "match_markets": len(markets),
        "db_total_records": db_total,
        "db_total_states": len(db_states),
        "db_total_districts": len(districts),
        "db_total_markets": len(markets),
    }

    latest = base_genuine.with_entities(func.max(MarketPrice.reporting_date)).scalar()
    age = (_date.today() - latest).days if latest else None

    series, series_counts = {}, {}
    for r in rows:
        if r.modal_price is None or r.reporting_date is None:
            continue
        series.setdefault(r.market_name, {})[r.reporting_date.isoformat()] = r.modal_price
        series_counts[r.market_name] = series_counts.get(r.market_name, 0) + 1
    top = sorted(series_counts, key=series_counts.get, reverse=True)[:5]
    labels = sorted({d for m in top for d in series[m]})
    chart = {"labels": labels,
             "datasets": [{"label": m, "data": [series[m].get(d) for d in labels]} for m in top]}

    last_sync = AuditLog.query.filter_by(action="mandi_sync").order_by(AuditLog.created_at.desc()).first()
    is_partial_sync = bool(last_sync and "partial" in (last_sync.detail or "").lower())

    flags = {}
    if rows:
        for fl in PriceFlag.query.filter(PriceFlag.price_id.in_([r.price_id for r in rows])).all():
            flags.setdefault(fl.price_id, []).append(fl.reason)
    lang = "en"
    my_alerts = (PriceAlert.query.filter_by(user_id=g.user.user_id, active=True).all()
                 if g.user and g.user.role in ("farmer", "buyer") else [])

    from market_agent import summary as market_summary
    STALE_DAYS = 7

    return render_template(
        "market.html",
        flags=flags, msum=market_summary(lang), lang=lang, my_alerts=my_alerts,
        industry=verified_industry_prices(), last_sync=last_sync, is_partial_sync=is_partial_sync,
        rows=rows, chart=chart,
        latest=latest, age=age, stale_days=STALE_DAYS,
        is_sample=False,
        only_sample=False,
        opts={"state": db_states, "district": districts, "market": markets, "variety": varieties},
        hierarchy=hierarchy,
        counts=counts,
        pagination=pagination,
        sort={"by": "date", "dir": "desc"},
        f={},
        rec_result=result,
        rec_form={
            "location": location, "variety": variety,
            "quantity": qty_raw, "unit": unit,
            "transport": transport_raw,
        },
    )


@bp.route("/market/data-status")
def market_data_status():
    """JSON endpoint: data collection agent status (for admin / debugging)."""
    return jsonify(data_collection_agent())
