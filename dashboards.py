"""
Role dashboards + verification + admin tools (blueprint "dash").
  /dashboard                 farmer / buyer / admin home (different content per role)
  /verification              farmer & buyer upload proof (land record / business licence)
  /admin/verifications ...   admin reviews proofs (humans approve; nothing is auto-verified)
  /admin/schemes ...         admin edits scheme records + multilingual text
  /admin/sync-prices         pull latest mandi prices from data.gov.in
  /admin/users, /admin/audit
"""
import io
import json
import os
import re
import uuid
from datetime import datetime

from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template, request,
                   send_from_directory, session, url_for)
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func

from access import audit, is_verified, login_required
from i18n import DOCS, LANGS, STAGE_ORDER, STAGES
from mandi_sync import sync
from market_agent import run_pipeline, summary as market_summary
import proof_agent
from matching import direct_offers, rank_demands_for_lot
from models import MarketPrice, ProductListing, Scheme, User, db
from models_market import (AuditLog, BuyerDemand, Deal, DemandResponse, FarmerProfile, Notification, SchemeInfo, UserProof)
from price_engine import baseline_for_location, industry_prices
from schemes_agent import _j, run

bp = Blueprint("dash", __name__)
PROOF_TYPES = {"farmer": ["Land record (7/12 or 8A)", "Other land document"],
               "buyer": ["Business licence", "GST registration", "FSSAI licence", "Other business document"]}


@bp.route("/dashboard")
@login_required()
def dashboard():
    u = g.user
    if u.role == "admin":
        return _admin_home()
    return _farmer_home() if u.role == "farmer" else _buyer_home()


def _proof_status(u):
    p = UserProof.query.filter_by(user_id=u.user_id).order_by(UserProof.created_at.desc()).first()
    return "approved" if is_verified(u) else (p.status if p else "none")


def _farmer_home():
    u = g.user
    lots = ProductListing.query.filter_by(farmer_id=u.user_id, listing_status="open").all()
    open_demands = BuyerDemand.query.filter_by(status="open").all()
    strong = 0
    best = None
    for l in lots:
        ranked = rank_demands_for_lot(l, open_demands)
        strong += sum(1 for r in ranked if not r["eval"]["fail_keys"])
        offers = direct_offers(ranked)
        if offers and (best is None or offers[0]["offer_q"] > best):
            best = offers[0]["offer_q"]
    fp = FarmerProfile.query.filter_by(user_id=u.user_id).first()
    cur_lang = session.get("lang") or (fp.language if fp and fp.language else "en")
    out = run(fp, cur_lang) if fp else None
    base = baseline_for_location((fp.district if fp else "") or "")
    return render_template(
        "dashboard_farmer.html", notes=Notification.query.filter_by(user_id=u.user_id, is_read=False)
        .order_by(Notification.created_at.desc()).limit(10).all(),
        msum=market_summary(cur_lang), proof=_proof_status(u), lots=lots, strong=strong, best_offer=best, fp=fp, out=out,
        base=base, n_resp=DemandResponse.query.filter_by(farmer_id=u.user_id).count(),
        deals=Deal.query.filter_by(farmer_id=u.user_id).filter(Deal.status.in_(["proposed", "confirmed", "delivered", "paid"])).all(),
        active_lang=cur_lang)


def _buyer_home():
    u = g.user
    demands = BuyerDemand.query.filter_by(buyer_id=u.user_id).all()
    ids = [d.demand_id for d in demands]
    new_resp = DemandResponse.query.filter(DemandResponse.demand_id.in_(ids), DemandResponse.status == "sent").count() if ids else 0
    return render_template("dashboard_buyer.html", proof=_proof_status(u), demands=demands, new_resp=new_resp,
                           deals=Deal.query.filter_by(buyer_id=u.user_id).filter(Deal.status.in_(["proposed", "confirmed", "delivered", "paid"])).all(),
                           board=industry_prices())


def _admin_home():
    last = AuditLog.query.filter_by(action="mandi_sync").order_by(AuditLog.created_at.desc()).first()
    return render_template(
        "dashboard_admin.html", pending=UserProof.query.filter_by(status="pending").count(),
        users=dict(db.session.query(User.role, func.count()).group_by(User.role).all()),
        deals=dict(db.session.query(Deal.status, func.count()).group_by(Deal.status).all()),
        n_prices=MarketPrice.query.count(), latest=db.session.query(func.max(MarketPrice.reporting_date)).scalar(),
        last_sync=last, logs=AuditLog.query.order_by(AuditLog.created_at.desc()).limit(12).all(),
        n_lots=ProductListing.query.count(), n_demands=BuyerDemand.query.count())


# ------------------------------------------------------------------ verification (farmer / buyer)
def _save_proof(f):
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in ("jpg", "jpeg", "png", "pdf"):
        return None, "Upload a JPG, PNG or PDF file."
    data = f.read()
    if not data:
        return None, "The file is empty."
    if ext == "pdf":
        if not data.startswith(b"%PDF"):
            return None, "That is not a valid PDF."
    else:
        try:
            Image.open(io.BytesIO(data)).verify()
        except (UnidentifiedImageError, OSError, SyntaxError):
            return None, "That is not a valid image."
    name = f"{uuid.uuid4().hex}.{ext}"
    os.makedirs(current_app.config["PROOF_FOLDER"], exist_ok=True)
    with open(os.path.join(current_app.config["PROOF_FOLDER"], name), "wb") as fh:
        fh.write(data)
    return name, None


@bp.route("/verification", methods=["GET", "POST"])
@login_required(roles=["farmer", "buyer"])
def verification():
    types = PROOF_TYPES[g.user.role]
    if request.method == "POST":
        f, doc = request.files.get("proof"), request.form.get("doc_type")
        if doc not in types or not f or not f.filename:
            flash("Choose the document type and a file.", "error")
        else:
            name, err = _save_proof(f)
            if err:
                flash(err, "error")
            else:
                proof = UserProof(user_id=g.user.user_id, doc_type=doc, filename=name)
                db.session.add(proof)
                db.session.flush()
                res = proof_agent.record(proof, os.path.join(current_app.config["PROOF_FOLDER"], name),
                                         name.rsplit(".", 1)[-1], g.user)
                audit("proof_uploaded", "user", g.user.user_id, doc)
                audit("agent_proof_read", "user", g.user.user_id, f"{res['mode']}: {len(res['flags'])} flag(s)")
                db.session.commit()
                flash("Proof uploaded. The admin will review it. Nothing is verified automatically.", "ok")
        return redirect(url_for("dash.verification"))
    proofs = UserProof.query.filter_by(user_id=g.user.user_id).order_by(UserProof.created_at.desc()).all()
    return render_template("verification.html", types=types, proofs=proofs, status=_proof_status(g.user))


# ------------------------------------------------------------------ admin
@bp.route("/admin/verifications")
@login_required(roles=["admin"])
def admin_verifications():
    rows = UserProof.query.order_by((UserProof.status == "pending").desc(), UserProof.created_at.desc()).limit(200).all()
    return render_template("admin_verifications.html", rows=rows)


@bp.route("/admin/proof/<int:pid>")
@login_required(roles=["admin"])
def admin_proof_file(pid):
    p = db.get_or_404(UserProof, pid)
    if not p.filename:
        abort(404)
    return send_from_directory(current_app.config["PROOF_FOLDER"], p.filename, as_attachment=True)


@bp.route("/admin/verifications/<int:pid>/review", methods=["POST"])
@login_required(roles=["admin"])
def admin_review(pid):
    p = db.get_or_404(UserProof, pid)
    decision = request.form.get("decision")
    if decision not in ("approved", "rejected"):
        abort(400)
    p.status, p.reviewed_by = decision, g.user.user_id
    p.admin_note = request.form.get("admin_note", "").strip()[:200] or None
    audit(f"proof_{decision}", "user", p.user_id, p.admin_note)
    db.session.commit()
    flash(f"{p.user.name}: {decision}.", "ok")
    return redirect(url_for("dash.admin_verifications"))


@bp.route("/admin/users")
@login_required(roles=["admin"])
def admin_users():
    rows = [(u, _proof_status(u)) for u in User.query.order_by(User.user_id.desc()).limit(300).all()]
    return render_template("admin_users.html", rows=rows)


@bp.route("/admin/admins", methods=["GET", "POST"])
@login_required(roles=["admin"])
def admin_admins():
    """Logged-in admins can create more admin accounts (no script needed)."""
    form = {}
    if request.method == "POST":
        form = request.form
        name, phone, pw = form.get("name", "").strip(), form.get("phone", "").strip(), form.get("password", "")
        errors = []
        if not 2 <= len(name) <= 100:
            errors.append("Enter the admin's name (2–100 characters).")
        if not re.match(r"^[6-9]\d{9}$", phone):
            errors.append("Enter a valid 10-digit Indian mobile number.")
        if len(pw) < 8:
            errors.append("Password must be at least 8 characters.")
        if pw != form.get("password2", ""):
            errors.append("The two passwords do not match.")
        if not errors and User.query.filter_by(phone=phone).first():
            errors.append("This mobile number is already registered.")
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            u = User(name=name, role="admin", phone=phone)
            u.set_password(pw)
            db.session.add(u)
            db.session.flush()
            audit("admin_created", "user", u.user_id, f"new admin {phone}")
            db.session.commit()
            flash(f"Admin account created for {name}. They can log in at the Admin login with {phone}.", "ok")
            return redirect(url_for("dash.admin_admins"))
    admins = User.query.filter_by(role="admin").order_by(User.user_id).all()
    return render_template("admin_admins.html", admins=admins, form=form), (400 if form else 200)


@bp.route("/admin/audit")
@login_required(roles=["admin"])
def admin_audit():
    return render_template("admin_audit.html", logs=AuditLog.query.order_by(AuditLog.created_at.desc()).limit(300).all())


@bp.route("/admin/sync-prices", methods=["POST"])
@login_required(roles=["admin"])
def admin_sync():
    res = run_pipeline(sync_fn=sync)        # orchestrator: sync -> flag odd records -> price alerts (all audited)
    ok, msg = res["sync"]
    flash(f"{msg} | {res['flagged']} record(s) flagged, {res['alerts']} alert(s) sent.", "ok" if ok else "error")
    return redirect(url_for("dash.dashboard"))


@bp.route("/admin/schemes")
@login_required(roles=["admin"])
def admin_schemes():
    return render_template("admin_schemes.html", rows=Scheme.query.order_by(Scheme.scheme_name).all())


@bp.route("/admin/schemes/<int:sid>", methods=["GET", "POST"])
@login_required(roles=["admin"])
def admin_scheme_edit(sid):
    s = db.get_or_404(Scheme, sid)
    info = SchemeInfo.query.filter_by(scheme_id=sid).first() or SchemeInfo(scheme_id=sid)
    if request.method == "POST":
        f, errors = request.form, []
        try:
            rules = json.loads(f.get("eligibility_rules") or "{}")
            if not isinstance(rules, dict):
                raise ValueError
        except ValueError:
            errors.append("Eligibility rules must be a JSON object, e.g. {\"owns_land\": true}.")
        url = f.get("official_url", "").strip()
        if not url.startswith("https://"):
            errors.append("Official URL must start with https://")
        verified = None
        if f.get("last_verified_date"):
            try:
                verified = datetime.strptime(f["last_verified_date"], "%Y-%m-%d").date()
            except ValueError:
                errors.append("Verification date is invalid.")
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            s.scheme_name, s.description = f["scheme_name"].strip(), f.get("description", "").strip()
            s.eligibility_text, s.benefits = f.get("eligibility_text", "").strip(), f.get("benefits", "").strip()
            s.required_documents, s.official_url, s.last_verified_date = f.get("required_documents", "").strip(), url, verified
            s.eligibility_rules = json.dumps(rules)
            info.stages = json.dumps([k for k in f.getlist("stages") if k in STAGES])
            info.required_docs = json.dumps([k for k in f.getlist("docs") if k in DOCS])
            info.names = json.dumps({l: f.get(f"name_{l}", "").strip() for l in LANGS})
            info.highlights = json.dumps({l: f.get(f"hl_{l}", "").strip() for l in LANGS})
            info.steps = json.dumps({l: [x.strip() for x in f.get(f"steps_{l}", "").splitlines() if x.strip()] for l in LANGS})
            db.session.add_all([s, info])
            audit("scheme_edited", "scheme", sid, s.scheme_name)
            db.session.commit()
            flash("Scheme saved.", "ok")
            return redirect(url_for("dash.admin_schemes"))
    return render_template("admin_scheme_edit.html", s=s, info=info, LANGS=LANGS, STAGES=STAGES, STAGE_ORDER=STAGE_ORDER,
                           DOCS=DOCS, stages=_j(info.stages, []), docs=_j(info.required_docs, []),
                           names=_j(info.names, {}), hl=_j(info.highlights, {}), steps=_j(info.steps, {}))
