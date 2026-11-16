"""
Deals + bill (blueprint "deals").
Flow: buyer proposes (from a farmer's response) -> farmer confirms -> farmer marks delivered
      -> buyer records payment reference -> farmer confirms money received (settled).
HaldiSetu does NOT process or hold payment (project-plan rule). The 'bill' is a sale record both
parties can print; payment happens directly between them, and the app only records the reference.
Contact details become visible only after the farmer confirms (both sides accepted).
"""
from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from access import audit, login_required, verified_required
from matching import UNIT_TO_QUINTAL, price_q, qty_q
from models import User, db
from models_market import Deal, DemandResponse

bp = Blueprint("deals", __name__)

STEPS = ["proposed", "confirmed", "delivered", "paid", "settled"]
# action -> (role allowed, statuses it can start from, resulting status)
TRANSITIONS = {
    "confirm": ("farmer", {"proposed"}, "confirmed"),
    "delivered": ("farmer", {"confirmed"}, "delivered"),
    "paid": ("buyer", {"delivered"}, "paid"),
    "settled": ("farmer", {"paid"}, "settled"),
    "cancel": (None, {"proposed", "confirmed"}, "cancelled"),
}


def _deal_for_user(did):
    d = db.get_or_404(Deal, did)
    if g.user.role != "admin" and g.user.user_id not in (d.farmer_id, d.buyer_id):
        abort(403)
    return d


def _num(s, lo, hi):
    try:
        v = float((s or "").strip())
        return v if lo < v <= hi else None
    except ValueError:
        return None


@bp.route("/responses/<int:rid>/deal", methods=["POST"])
@login_required(roles=["buyer"])
@verified_required
def propose(rid):
    r = db.get_or_404(DemandResponse, rid)
    dem, lot = r.demand, r.listing
    if dem.buyer_id != g.user.user_id:
        abort(403)
    back = redirect(url_for("mp.demand_detail", did=dem.demand_id))
    if r.deal:
        flash("A deal already exists for this offer.", "warn")
        return back
    qty = _num(request.form.get("quantity_q"), 0, 1_000_000)
    price = _num(request.form.get("price_per_q"), 0, 10_000_000)
    if qty is None or price is None:
        flash("Enter a valid quantity (quintals) and price (₹ per quintal).", "error")
        return back
    if lot.listing_status != "open" or dem.status != "open":
        flash("The lot or the demand is no longer open.", "error")
        return back
    if qty > qty_q(lot.quantity, lot.quantity_unit) + 1e-9:
        flash("Quantity is more than the farmer's available lot.", "error")
        return back
    deal = Deal(response_id=r.response_id, demand_id=dem.demand_id, listing_id=lot.listing_id, farmer_id=lot.farmer_id,
                buyer_id=g.user.user_id, quantity_q=qty, price_per_q=price, total=round(qty * price, 2))
    db.session.add(deal)
    db.session.flush()
    deal.bill_no = f"HS-{date.today():%Y%m%d}-{deal.deal_id:05d}"
    r.status = "shortlisted"
    audit("deal_proposed", "deal", deal.deal_id, f"{qty:g} q @ ₹{price:,.0f}")
    db.session.commit()
    flash("Deal proposed. The farmer must confirm it before contact details are shared.", "ok")
    return redirect(url_for("deals.detail", did=deal.deal_id))


@bp.route("/deals")
@login_required(roles=["farmer", "buyer", "admin"])
def listing():
    q = Deal.query
    if g.user.role == "farmer":
        q = q.filter_by(farmer_id=g.user.user_id)
    elif g.user.role == "buyer":
        q = q.filter_by(buyer_id=g.user.user_id)
    return render_template("deals.html", rows=q.order_by(Deal.created_at.desc()).all())


@bp.route("/connections")
@login_required(roles=["farmer", "buyer"])
def connections():
    """Matched farmer/buyer pairs whose deal the farmer has confirmed: contact details are shared here."""
    mine = Deal.farmer_id == g.user.user_id if g.user.role == "farmer" else Deal.buyer_id == g.user.user_id
    rows = (Deal.query.filter(mine, Deal.status.in_(["confirmed", "delivered", "paid", "settled"]))
            .order_by(Deal.created_at.desc()).all())
    other = (lambda x: x.buyer_id) if g.user.role == "farmer" else (lambda x: x.farmer_id)
    return render_template("connections.html", pairs=[(x, db.session.get(User, other(x))) for x in rows])


@bp.route("/deals/<int:did>")
@login_required(roles=["farmer", "buyer", "admin"])
def detail(did):
    d = _deal_for_user(did)
    return render_template("deal_detail.html", d=d, steps=STEPS,
                           reveal=d.status in ("confirmed", "delivered", "paid", "settled") or g.user.role == "admin")


@bp.route("/deals/<int:did>/action", methods=["POST"])
@login_required(roles=["farmer", "buyer"])
def action(did):
    d = _deal_for_user(did)
    act = request.form.get("action")
    if act not in TRANSITIONS:
        abort(400)
    role, allowed_from, new = TRANSITIONS[act]
    if (role and g.user.role != role) or d.status not in allowed_from:
        flash("That action is not available at this stage.", "error")
        return redirect(url_for("deals.detail", did=did))
    lot = d.listing
    if act == "confirm":
        if qty_q(lot.quantity, lot.quantity_unit) + 1e-9 < d.quantity_q or lot.listing_status != "open":
            flash("Your lot no longer has this quantity available.", "error")
            return redirect(url_for("deals.detail", did=did))
        lot.quantity = max(0.0, lot.quantity - d.quantity_q / UNIT_TO_QUINTAL[lot.quantity_unit])
        if lot.quantity <= 1e-9:
            lot.listing_status = "closed"
    if act == "cancel" and d.status == "confirmed":      # give the quantity back
        lot.quantity += d.quantity_q / UNIT_TO_QUINTAL[lot.quantity_unit]
        lot.listing_status = "open"
    if act == "paid":
        ref = request.form.get("payment_ref", "").strip()
        if not 3 <= len(ref) <= 60:
            flash("Enter the payment reference (UPI/UTR/cheque no.), 3–60 characters.", "error")
            return redirect(url_for("deals.detail", did=did))
        d.payment_ref = ref
    d.status = new
    audit(f"deal_{act}", "deal", d.deal_id, f"-> {new}")
    db.session.commit()
    flash(f"Deal updated: {new}.", "ok")
    return redirect(url_for("deals.detail", did=did))


@bp.route("/deals/<int:did>/bill")
@login_required(roles=["farmer", "buyer", "admin"])
def bill(did):
    d = _deal_for_user(did)
    if d.status in ("proposed", "cancelled"):
        flash("A bill is available after the farmer confirms the deal.", "warn")
        return redirect(url_for("deals.detail", did=did))
    return render_template("bill.html", d=d, mandi_ref=price_q(d.listing.expected_price, d.listing.price_unit))
