"""Module 3 — Government schemes (blueprint "sch"). Farmer profile -> rule-based agent -> multilingual plan."""
import json

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from access import audit, login_required
from i18n import DOCS, LANGS, STAGE_ORDER, STAGES, tr
from models import Scheme, db
from models_market import FarmerProfile, SchemeInfo
from schemes_agent import _j, _loc, run

bp = Blueprint("sch", __name__)
FARMER_TYPES = ["owner", "tenant", "sharecropper"]
STATES = ["Andhra Pradesh", "Assam", "Bihar", "Gujarat", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra",
          "Odisha", "Tamil Nadu", "Telangana", "Uttar Pradesh", "West Bengal", "Other"]


@bp.route("/schemes")
def schemes():
    lang = request.args.get("lang")
    fp = None
    if g.user and g.user.role == "farmer":
        fp = FarmerProfile.query.filter_by(user_id=g.user.user_id).first()
    if lang not in LANGS:
        lang = (fp.language if fp and fp.language in LANGS else "en")
    ctx = dict(lang=lang, L=tr(lang), LANGS=LANGS, STAGES=STAGES, STAGE_ORDER=STAGE_ORDER, DOCS=DOCS,
               STATES=STATES, FARMER_TYPES=FARMER_TYPES, fp=fp, out=None, have=set(), public=[])
    if g.user and g.user.role == "farmer":
        if fp:
            ctx["out"] = run(fp, lang)
            ctx["have"] = set(_j(fp.docs, []))
    else:  # visitors / buyers / admin: just the public list of scheme names in the chosen language
        for s in Scheme.query.order_by(Scheme.scheme_name).all():
            info = SchemeInfo.query.filter_by(scheme_id=s.scheme_id).first()
            ctx["public"].append({"name": _loc(_j(info.names, {}), lang, s.scheme_name) if info else s.scheme_name,
                                  "url": s.official_url, "text": _loc(_j(info.highlights, {}), lang, s.description) if info else s.description})
    return render_template("schemes.html", **ctx)


@bp.route("/schemes/profile", methods=["POST"])
@login_required(roles=["farmer"])
def save_profile():
    f, errors = request.form, []
    land = None
    if f.get("land_ha", "").strip():
        try:
            land = float(f["land_ha"])
            if not 0 <= land <= 10000:
                raise ValueError
        except ValueError:
            errors.append("Land must be a number between 0 and 10000 hectares.")
    if f.get("state") and f["state"] not in STATES:
        errors.append("Choose a valid state.")
    if f.get("owns_land") not in ("", "yes", "no", None):
        errors.append("Invalid land ownership answer.")
    if f.get("farmer_type") not in ["", *FARMER_TYPES]:
        errors.append("Invalid farmer category.")
    if f.get("stage") not in ["", *STAGE_ORDER]:
        errors.append("Invalid farming stage.")
    lang = f.get("language") if f.get("language") in LANGS else "en"
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("sch.schemes", lang=lang))
    fp = FarmerProfile.query.filter_by(user_id=g.user.user_id).first() or FarmerProfile(user_id=g.user.user_id)
    fp.state, fp.district = f.get("state") or None, (f.get("district", "").strip()[:60] or None)
    fp.land_ha, fp.owns_land = land, f.get("owns_land") or None
    fp.farmer_type, fp.stage = f.get("farmer_type") or None, f.get("stage") or None
    fp.docs = json.dumps([d for d in f.getlist("docs") if d in DOCS])
    fp.language = lang
    db.session.add(fp)
    audit("scheme_profile_saved", "farmer_profile", g.user.user_id)
    db.session.commit()
    flash("Saved.", "ok")
    return redirect(url_for("sch.schemes", lang=lang))
