"""
Direct Farmer-to-Industry Marketplace (blueprint "mp").
  buyers post demands  ->  farmers keep a quality card per lot  ->  engine matches + explains
  ->  farmer responds with a lot  ->  buyer shortlists.   Plus lot-specific price intelligence.
"""
from datetime import date, datetime

from flask import (Blueprint, abort, flash, g, redirect, render_template, request, url_for)

from access import audit, login_required, verified_required
from matching import direct_offers, evaluate, group_suggestion, price_q, rank_demands_for_lot, rank_lots_for_demand
from models import ProductListing, db
from models_agent import MatchProposal
from models_market import INDUSTRIES, BuyerDemand, DemandResponse, LotQuality
import agent_triggers
from agent_notifications import notify_user
from price_engine import fresh_vs_dried, price_card, sell_when
from agent_triggers import on_new_lot, on_new_requirement

bp = Blueprint("mp", __name__)
DEMAND_FORMS = ["Any form", "Fresh rhizome", "Dried turmeric (finger)", "Dried turmeric (bulb)",
                "Polished turmeric", "Turmeric powder"]
QTY_UNITS = ["Quintal", "Kg", "Tonne"]
PRICE_UNITS = ["Rs/Quintal", "Rs/Kg"]


def _date(s):
    try:
        return datetime.strptime((s or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _opt_float(s, lo, hi, label, errors):
    s = (s or "").strip()
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        errors.append(f"{label} must be a number.")
        return None
    if not lo <= v <= hi:
        errors.append(f"{label} must be between {lo:g} and {hi:g}.")
        return None
    return v


def parse_quality(form):
    """Shared by the listing form and the quality-card editor. Returns (values dict, errors list)."""
    errors = []
    harvest = None
    if form.get("harvest_date"):
        harvest = _date(form["harvest_date"])
        if not harvest:
            errors.append("Harvest date is not valid.")
    vals = {
        "variety": (form.get("variety") or "").strip()[:60] or None,
        "moisture_pct": _opt_float(form.get("moisture_pct"), 0, 100, "Moisture %", errors),
        "curcumin_pct": _opt_float(form.get("curcumin_pct"), 0, 100, "Curcumin %", errors),
        "has_lab_report": form.get("has_lab_report") == "on",
        "lab_report_ref": (form.get("lab_report_ref") or "").strip()[:120] or None,
        "polished": form.get("polished") == "on",
        "harvest_date": harvest,
    }
    if vals["has_lab_report"] and not vals["lab_report_ref"]:
        errors.append("Enter the lab report reference (lab name / report number) if you have a lab report.")
    return vals, errors


def save_quality(listing_id, vals):
    q = LotQuality.query.filter_by(listing_id=listing_id).first() or LotQuality(listing_id=listing_id)
    for k, v in vals.items():
        setattr(q, k, v)
    db.session.add(q)


def _open_lots():
    return ProductListing.query.filter_by(listing_status="open").all()


def _open_demands():
    return BuyerDemand.query.filter_by(status="open").order_by(BuyerDemand.created_at.desc()).all()


# ------------------------------------------------------------------ hub + demands
@bp.route("/marketplace")
def hub():
    return render_template("marketplace.html", demands=_open_demands()[:4],
                           n_demands=BuyerDemand.query.filter_by(status="open").count(),
                           n_lots=ProductListing.query.filter_by(listing_status="open").count(),
                           n_resp=DemandResponse.query.count())


@bp.route("/demands")
def demands():
    q = BuyerDemand.query.filter_by(status="open")
    if request.args.get("industry") in INDUSTRIES:
        q = q.filter_by(industry_type=request.args["industry"])
    return render_template("demands.html", rows=q.order_by(BuyerDemand.created_at.desc()).all(),
                           industries=INDUSTRIES, f=request.args)


@bp.route("/demands/new", methods=["GET", "POST"])
@login_required(roles=["buyer"])
@verified_required
def demand_new():
    ctx = dict(industries=INDUSTRIES, forms=DEMAND_FORMS, qty_units=QTY_UNITS, price_units=PRICE_UNITS)
    if request.method == "POST":
        f, errors = request.form, []
        qty = _opt_float(f.get("quantity"), 0.01, 1_000_000, "Quantity", errors)
        price = _opt_float(f.get("offered_price"), 0.01, 10_000_000, "Offered price", errors)
        if qty is None and not errors:
            errors.append("Quantity is required.")
        if price is None and not errors:
            errors.append("Offered price is required.")
        if f.get("industry_type") not in INDUSTRIES:
            errors.append("Choose your industry.")
        if f.get("product_form") not in DEMAND_FORMS:
            errors.append("Choose a product form.")
        if f.get("quantity_unit") not in QTY_UNITS or f.get("price_unit") not in PRICE_UNITS:
            errors.append("Choose valid units.")
        if not 3 <= len(f.get("delivery_location", "").strip()) <= 120:
            errors.append("Enter the delivery location.")
        by = None
        if f.get("deliver_by"):
            by = _date(f["deliver_by"])
            if not by or by < date.today():
                errors.append("Delivery date must be a valid future date.")
        min_c = _opt_float(f.get("min_curcumin"), 0, 100, "Minimum curcumin %", errors)
        max_m = _opt_float(f.get("max_moisture"), 0, 100, "Maximum moisture %", errors)
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("demand_form.html", form=f, **ctx), 400
        d = BuyerDemand(buyer_id=g.user.user_id, industry_type=f["industry_type"], product_form=f["product_form"],
                        quantity=qty, quantity_unit=f["quantity_unit"], delivery_location=f["delivery_location"].strip(),
                        deliver_by=by, offered_price=price, price_unit=f["price_unit"], min_curcumin=min_c,
                        max_moisture=max_m, requires_lab_report=f.get("requires_lab_report") == "on",
                        notes=f.get("notes", "").strip()[:300] or None)
        db.session.add(d)
        db.session.flush()  # assigns demand_id so the audit row can reference it
        audit("demand_posted", "demand", d.demand_id, f"{d.industry_type}: {d.quantity:g} {d.quantity_unit}")
        db.session.commit()
        on_new_requirement(d.demand_id)      # AI agent searches open lots in the background
        flash("Demand posted. The AI is matching it with farmers' lots; check AI Matches shortly.", "ok")
        return redirect(url_for("mp.demand_detail", did=d.demand_id))
    return render_template("demand_form.html", form={}, **ctx)


@bp.route("/demands/<int:did>")
def demand_detail(did):
    d = db.get_or_404(BuyerDemand, did)
    lots = _open_lots()
    ctx = {"d": d, "group": group_suggestion(d, lots), "ranked": None, "responded": set(), "responses": None}
    if g.user and g.user.role == "farmer":
        ctx["ranked"] = rank_lots_for_demand(d, [l for l in lots if l.farmer_id == g.user.user_id])
        ctx["responded"] = {r.listing_id for r in d.responses if r.farmer_id == g.user.user_id}
    if g.user and g.user.user_id == d.buyer_id:
        ctx["responses"] = sorted(((r, evaluate(r.listing, d)) for r in d.responses),
                                  key=lambda x: (len(x[1]["fail_keys"]), -x[1]["score"]))
    return render_template("demand_detail.html", **ctx)


@bp.route("/demands/<int:did>/respond", methods=["POST"])
@login_required(roles=["farmer"])
@verified_required
def respond(did):
    d = db.get_or_404(BuyerDemand, did)
    lot = db.session.get(ProductListing, request.form.get("listing_id", type=int) or 0)
    errors = []
    if d.status != "open":
        errors.append("This demand is closed.")
    if not lot or lot.farmer_id != g.user.user_id or lot.listing_status != "open":
        errors.append("Choose one of your open lots.")
    ask = _opt_float(request.form.get("ask_price"), 0.01, 10_000_000, "Asking price", errors)
    msg = request.form.get("message", "").strip()[:300] or None
    if not errors and DemandResponse.query.filter_by(demand_id=did, listing_id=lot.listing_id).first():
        errors.append("You have already offered this lot to this buyer.")
    if errors:
        for e in errors:
            flash(e, "error")
    else:
        db.session.add(DemandResponse(demand_id=did, listing_id=lot.listing_id, farmer_id=g.user.user_id,
                                      ask_price=ask, message=msg, match_score=evaluate(lot, d)["score"]))
        audit("lot_offered", "demand", did, f"lot {lot.listing_id}")
        db.session.commit()
        flash("Your lot was sent to the buyer. This is an offer, not a completed sale.", "ok")
    return redirect(url_for("mp.demand_detail", did=did))


@bp.route("/responses/<int:rid>/status", methods=["POST"])
@login_required(roles=["buyer"])
def response_status(rid):
    r = db.get_or_404(DemandResponse, rid)
    if r.demand.buyer_id != g.user.user_id:
        abort(403)
    if request.form.get("status") not in ("sent", "shortlisted", "declined"):
        abort(400)
    r.status = request.form["status"]
    db.session.commit()
    return redirect(url_for("mp.demand_detail", did=r.demand_id))


@bp.route("/demands/<int:did>/toggle", methods=["POST"])
@login_required(roles=["buyer"])
def demand_toggle(did):
    d = db.get_or_404(BuyerDemand, did)
    if d.buyer_id != g.user.user_id:
        abort(403)
    d.status = "closed" if d.status == "open" else "open"
    db.session.commit()
    return redirect(url_for("mp.my_demands"))


@bp.route("/my/demands")
@login_required(roles=["buyer"])
def my_demands():
    rows = BuyerDemand.query.filter_by(buyer_id=g.user.user_id).order_by(BuyerDemand.created_at.desc()).all()
    return render_template("my_demands.html", rows=rows)


# ------------------------------------------------------------------ lot dashboard (quality card, matches, price)
def _own_lot(lid):
    lot = db.get_or_404(ProductListing, lid)
    if lot.farmer_id != g.user.user_id:
        abort(403)
    return lot


@bp.route("/lots/<int:lid>")
@login_required(roles=["farmer"])
def lot(lid):
    l = _own_lot(lid)
    ranked = rank_demands_for_lot(l, _open_demands())
    price = price_card(l, direct_offers(ranked))
    storage = None
    raw = request.args.get("storage_cost", "").strip()
    if raw:
        errs = []
        storage = _opt_float(raw, 0, 1_000_000, "Storage cost", errs)
        for e in errs:
            flash(e, "error")
    sw = sell_when(price["base"]["markets"], storage) if price["base"] else None
    return render_template("lot.html", l=l, ranked=ranked, price=price, sw=sw, storage=storage)


@bp.route("/lots/<int:lid>/quality", methods=["GET", "POST"])
@login_required(roles=["farmer"])
def lot_quality(lid):
    l = _own_lot(lid)
    if request.method == "POST":
        vals, errors = parse_quality(request.form)
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("lot_quality_form.html", l=l, form=request.form), 400
        save_quality(lid, vals)
        db.session.commit()
        on_new_lot(lid)                      # better quality data can unlock new matches
        flash("Quality card saved. Matches have been recalculated.", "ok")
        return redirect(url_for("mp.lot", lid=lid))
    q = l.quality
    form = {} if not q else {"variety": q.variety or "", "moisture_pct": q.moisture_pct if q.moisture_pct is not None else "",
                             "curcumin_pct": q.curcumin_pct if q.curcumin_pct is not None else "",
                             "has_lab_report": "on" if q.has_lab_report else "", "lab_report_ref": q.lab_report_ref or "",
                             "polished": "on" if q.polished else "",
                             "harvest_date": q.harvest_date.isoformat() if q.harvest_date else ""}
    return render_template("lot_quality_form.html", l=l, form=form)


# ------------------------------------------------------------------ calculator
@bp.route("/tools/fresh-vs-dried")
def tool_fresh_dried():
    a, errors, res = request.args, [], None
    if a.get("fresh_q") is not None:
        vals = {k: _opt_float(a.get(k), 0.0001, 1e9, lbl, errors) for k, lbl in
                (("fresh_q", "Fresh quantity"), ("fresh_price", "Fresh price"), ("dried_price", "Dried price"),
                 ("ratio", "Fresh-to-dry ratio"))}
        cost = _opt_float(a.get("cost") or "0", 0, 1e9, "Processing cost", errors)
        if not errors and all(v is not None for v in vals.values()):
            res = fresh_vs_dried(vals["fresh_q"], vals["fresh_price"], vals["dried_price"], vals["ratio"], cost or 0)
        elif not errors:
            errors.append("Fill in all required fields.")
    for e in errors:
        flash(e, "error")
    return render_template("tool_fresh_dried.html", res=res, a=a)


# ------------------------------------------------------------------ AI matches + connection
# Flow: AI agent proposes a match (score is computed by matching.py, never by the LLM)
#   -> farmer clicks "Offer my lot" (creates the DemandResponse the buyer already sees)
#   -> buyer shortlists / proposes a deal -> farmer confirms -> phone numbers become visible (deals.py).
# Buyers can click "I'm interested" to nudge the farmer. No contact details are shown on this page.
def _my_proposals():
    """(proposal, lot, demand, eval, response) for the current user's still-relevant proposals."""
    rows = []
    for p in MatchProposal.query.filter(MatchProposal.status != "dismissed").order_by(MatchProposal.score.desc()).all():
        lot, d = db.session.get(ProductListing, p.lot_id), db.session.get(BuyerDemand, p.requirement_id)
        if not lot or not d or g.user.user_id not in (lot.farmer_id, d.buyer_id):
            continue
        resp = DemandResponse.query.filter_by(demand_id=d.demand_id, listing_id=lot.listing_id).first()
        if not resp and (lot.listing_status != "open" or d.status != "open"):
            continue
        rows.append({"p": p, "lot": lot, "d": d, "ev": evaluate(lot, d), "resp": resp})
    return rows


@bp.route("/matches")
@login_required(roles=["farmer", "buyer"])
def matches():
    return render_template("matches.html", rows=_my_proposals(), ai_mode=agent_triggers.ai_mode())


@bp.route("/matches/refresh", methods=["POST"])
@login_required(roles=["farmer", "buyer"])
def matches_refresh():
    """Ask the AI to search again for all of my open lots (farmer) or open demands (buyer)."""
    if g.user.role == "farmer":
        ids = [l.listing_id for l in ProductListing.query.filter_by(farmer_id=g.user.user_id, listing_status="open")]
        for i in ids:
            on_new_lot(i)
    else:
        ids = [d.demand_id for d in BuyerDemand.query.filter_by(buyer_id=g.user.user_id, status="open")]
        for i in ids:
            on_new_requirement(i)
    flash(f"AI is searching for matches for {len(ids)} item(s). Reload this page in a few seconds." if ids
          else "You have nothing open to match yet.", "ok" if ids else "warn")
    return redirect(url_for("mp.matches"))


def _proposal_for_user(pid):
    p = db.get_or_404(MatchProposal, pid)
    lot, d = db.session.get(ProductListing, p.lot_id), db.session.get(BuyerDemand, p.requirement_id)
    if not lot or not d or g.user.user_id not in (lot.farmer_id, d.buyer_id):
        abort(403)
    return p, lot, d


@bp.route("/matches/<int:pid>/accept", methods=["POST"])
@login_required(roles=["farmer"])
@verified_required
def match_accept(pid):
    """Farmer agrees to the AI match: the lot is offered to the buyer (same as the manual Offer button)."""
    p, lot, d = _proposal_for_user(pid)
    if lot.farmer_id != g.user.user_id:
        abort(403)
    if d.status != "open" or lot.listing_status != "open":
        flash("This lot or demand is no longer open.", "error")
    elif DemandResponse.query.filter_by(demand_id=d.demand_id, listing_id=lot.listing_id).first():
        flash("You have already offered this lot to this buyer.", "warn")
    else:
        db.session.add(DemandResponse(demand_id=d.demand_id, listing_id=lot.listing_id, farmer_id=g.user.user_id,
                                      ask_price=price_q(lot.expected_price, lot.price_unit),
                                      message="Offered via AI match", match_score=evaluate(lot, d)["score"]))
        p.status = "accepted"
        audit("ai_match_accepted", "demand", d.demand_id, f"lot {lot.listing_id}, proposal {p.id}")
        db.session.commit()
        notify_user(d.buyer_id, f"A farmer offered Lot #{lot.listing_id} for your demand #{d.demand_id} "
                                "(AI match). Open the demand to shortlist it or propose a deal.", kind="match")
        flash("Offer sent to the buyer. Contact details are shared only after a deal is confirmed.", "ok")
    return redirect(url_for("mp.matches"))


@bp.route("/matches/<int:pid>/interest", methods=["POST"])
@login_required(roles=["buyer"])
def match_interest(pid):
    """Buyer likes the matched lot: tell the farmer (no contact details are exchanged)."""
    p, lot, d = _proposal_for_user(pid)
    if d.buyer_id != g.user.user_id:
        abort(403)
    if p.status == "proposed":
        p.status = "interested"
        audit("ai_match_interest", "demand", d.demand_id, f"lot {lot.listing_id}, proposal {p.id}")
        db.session.commit()
        notify_user(lot.farmer_id, f"A buyer ({d.industry_type}, demand #{d.demand_id}) is interested in your "
                                   f"Lot #{lot.listing_id}. Open AI Matches and offer it to connect.", kind="match")
        flash("The farmer has been told you are interested.", "ok")
    return redirect(url_for("mp.matches"))


@bp.route("/matches/<int:pid>/dismiss", methods=["POST"])
@login_required(roles=["farmer", "buyer"])
def match_dismiss(pid):
    p, lot, d = _proposal_for_user(pid)
    p.status = "dismissed"
    db.session.commit()
    return redirect(url_for("mp.matches"))
