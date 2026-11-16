"""
HaldiSetu — Flask application (Member 2: web app, database, Modules 3 & 4, integration).

Sections:  helpers/auth  |  Module 1+2 (detect + advisory)  |  Module 3 (schemes)
           Module 4 (market + listings + enquiries)  |  admin  |  error handlers
Run:  python app.py        (or: flask --app app run --debug)
"""
import os
import re
import secrets
import uuid
from datetime import date, datetime
from functools import wraps
from auto_refresh import is_due, kick, start_background

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func

from access import audit, verified_required
from agents_module import bp as ag_bp
from agent_triggers import on_new_lot
from agent_routes import agent_bp
import models_agent  # noqa: F401  (registers the agent_* tables)
from market_agent import run_pipeline, summary as market_summary
from config import Config
from dashboards import bp as dash_bp
from deals import bp as deals_bp
from marketplace import bp as mp_bp, parse_quality, save_quality
from schemes_module import bp as sch_bp
from ml.inference import get_predictor
from models import (BuyerEnquiry, DiseaseAdvisory, DiseasePrediction, MarketPrice,
                    ProductListing, Scheme, User, db)
from matching import qty_q
from models_market import AuditLog, FarmerProfile, PriceAlert, PriceFlag  # noqa: F401  (imports register all marketplace tables)
from price_engine import industry_prices, verified_industry_prices
from price_import import import_csv_text

STALE_DAYS = 7  # market records older than this are labelled "Historical"
PRODUCT_FORMS = ["Fresh rhizome", "Dried turmeric (finger)", "Dried turmeric (bulb)",
                 "Polished turmeric", "Turmeric powder"]
QTY_UNITS = ["Quintal", "Kg", "Tonne"]
PRICE_UNITS = ["Rs/Quintal", "Rs/Kg"]
STATES = ["Andhra Pradesh", "Assam", "Bihar", "Gujarat", "Karnataka", "Kerala", "Madhya Pradesh",
          "Maharashtra", "Odisha", "Tamil Nadu", "Telangana", "Uttar Pradesh", "West Bengal", "Other"]
PHONE_RE = re.compile(r"^[6-9]\d{9}$")


def _bootstrap_admin(app):
    """If no admin exists yet, create one from ADMIN_PHONE / ADMIN_PASSWORD in .env (skipped in tests)."""
    if app.config.get("TESTING") or User.query.filter_by(role="admin").first():
        return
    phone, pw = os.getenv("ADMIN_PHONE", "").strip(), os.getenv("ADMIN_PASSWORD", "")
    if PHONE_RE.match(phone) and len(pw) >= 8 and not User.query.filter_by(phone=phone).first():
        u = User(name="Administrator", role="admin", phone=phone)
        u.set_password(pw)
        db.session.add(u)
        db.session.commit()


def create_app(overrides=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    app.config.setdefault("PROOF_FOLDER", os.path.join(os.path.dirname(os.path.abspath(__file__)), "private_uploads"))
    for bp in (sch_bp, mp_bp, deals_bp, dash_bp, ag_bp, agent_bp):
        app.register_blueprint(bp)
    db.init_app(app)
    with app.app_context():
        db.create_all()
        _bootstrap_admin(app)
        start_background(app)

    # ------------------------------------------------------------------ helpers / auth
    def csrf_token():
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_hex(16)
        return session["_csrf"]

    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["qty_q"] = qty_q
    app.jinja_env.filters["inr"] = lambda v: "—" if v is None else f"₹{v:,.0f}"
    app.jinja_env.filters["dmy"] = lambda d: d.strftime("%d %b %Y") if d else "—"

    @app.before_request
    def load_user_and_check_csrf():
        g.user = db.session.get(User, session["uid"]) if "uid" in session else None
        if "lang" in request.args and request.args["lang"] in ("en", "mr", "hi"):
            session["lang"] = request.args["lang"]
        if "lang" not in session:
            if g.user and g.user.role == "farmer":
                fp = FarmerProfile.query.filter_by(user_id=g.user.user_id).first()
                if fp and fp.language in ("en", "mr", "hi"):
                    session["lang"] = fp.language
            if "lang" not in session:
                session["lang"] = "en"
        g.lang = session["lang"]
        if request.method == "POST":
            sent = request.form.get("_csrf", "")
            if not sent or not secrets.compare_digest(sent, session.get("_csrf", "")):
                abort(400, "Invalid or missing form token. Reload the page and try again.")

    @app.context_processor
    def inject_globals():
        cur_lang = session.get("lang") or getattr(g, "lang", "en")
        return {"user": g.get("user"), "today": date.today(), "STATES": STATES,
                "lang": cur_lang, "active_lang": cur_lang}

    @app.route("/set-language/<lang>")
    def set_language(lang):
        if lang in ("en", "mr", "hi"):
            session["lang"] = lang
            if g.user and g.user.role == "farmer":
                fp = FarmerProfile.query.filter_by(user_id=g.user.user_id).first()
                if fp:
                    fp.language = lang
                    db.session.commit()
        nxt = request.args.get("next") or request.referrer or url_for("dash.dashboard")
        return redirect(nxt)

    def login_required(roles=None):
        def deco(fn):
            @wraps(fn)
            def wrapper(*a, **kw):
                if not g.user:
                    flash("Please log in to continue.", "warn")
                    return redirect(url_for("login", next=request.path))
                if roles and g.user.role not in roles:
                    abort(403)
                return fn(*a, **kw)
            return wrapper
        return deco

    def parse_date(s):
        try:
            return datetime.strptime((s or "").strip(), "%Y-%m-%d").date()
        except ValueError:
            return None

    # ------------------------------------------------------------------ home + auth
    @app.route("/")
    def index():
        stats = {
            "schemes": Scheme.query.count(),
            "prices": MarketPrice.query.count(),
            "listings": ProductListing.query.filter_by(listing_status="open").count(),
            "latest_price": db.session.query(func.max(MarketPrice.reporting_date)).scalar(),
        }
        return render_template("index.html", stats=stats)

    ROLE_LABEL = {"farmer": "Farmer", "buyer": "Buyer", "admin": "Admin"}

    # Separate doors: /login/farmer and /login/buyer (and /register/farmer, /register/buyer).
    # /login and /register (no role) show a chooser page, so existing url_for('login') links still work.
    @app.route("/register", methods=["GET"], defaults={"role": None})
    @app.route("/register/<role>", methods=["GET", "POST"])
    def register(role):
        if role is None:
            return render_template("register_choose.html")
        if role not in ("farmer", "buyer"):          # admins are never self-registered
            abort(404)
        if request.method == "POST":
            f = request.form
            name, phone, pw = f.get("name", "").strip(), f.get("phone", "").strip(), f.get("password", "")
            errors = []
            if not 2 <= len(name) <= 100:
                errors.append("Enter your name (2–100 characters).")
            if not PHONE_RE.match(phone):
                errors.append("Enter a valid 10-digit Indian mobile number.")
            if len(pw) < 8:
                errors.append("Password must be at least 8 characters.")
            if not errors and User.query.filter_by(phone=phone).first():
                errors.append("This mobile number is already registered.")
            if errors:
                for e in errors:
                    flash(e, "error")
                return render_template("register.html", form=f, role=role, role_label=ROLE_LABEL[role]), 400
            # the role comes from the URL, never from the form, so nobody can choose or fake it
            u = User(name=name, role=role, phone=phone, district=f.get("district", "").strip()[:80] or None)
            u.set_password(pw)
            db.session.add(u)
            db.session.commit()
            flash("Account created. Please log in.", "ok")
            return redirect(url_for("login", role=role))
        return render_template("register.html", form={}, role=role, role_label=ROLE_LABEL[role])

    @app.route("/login", methods=["GET"], defaults={"role": None})
    @app.route("/login/<role>", methods=["GET", "POST"])
    def login(role):
        if role is None:
            return render_template("login_choose.html", next=request.args.get("next", ""))
        if role not in ROLE_LABEL:                    # /login/admin works but has no public button
            abort(404)
        if request.method == "POST":
            u = User.query.filter_by(phone=request.form.get("phone", "").strip()).first()
            if not u or not u.check_password(request.form.get("password", "")):
                flash("Wrong mobile number or password.", "error")
            elif u.role != role:
                flash(f"This is a {ROLE_LABEL.get(u.role, u.role)} account. "
                      f"Please use the {ROLE_LABEL.get(u.role, u.role)} login.", "error")
            else:
                session.clear()
                session["uid"] = u.user_id
                nxt = request.args.get("next", "")
                flash(f"Welcome, {u.name}.", "ok")
                return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("dash.dashboard"))
            return render_template("login.html", role=role, role_label=ROLE_LABEL[role]), 401
        return render_template("login.html", role=role, role_label=ROLE_LABEL[role])

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        flash("Logged out.", "ok")
        return redirect(url_for("index"))

    # ------------------------------------------------------------------ Module 1 + 2: detect + advisory
    @app.route("/detect", methods=["GET", "POST"])
    def detect():
        if request.method == "GET":
            return render_template("detect.html")
        f = request.files.get("leaf_image")
        if not f or not f.filename:
            flash("Please choose a leaf image first.", "error")
            return redirect(url_for("detect"))
        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
        if ext not in app.config["ALLOWED_EXTENSIONS"]:
            flash("Only JPG, JPEG or PNG images are accepted.", "error")
            return redirect(url_for("detect"))
        try:
            probe = Image.open(f.stream)
            if probe.format not in ("JPEG", "PNG"):
                raise ValueError("format")
            w, h = probe.size
            if w * h > 25_000_000:
                flash("Image dimensions are too large. Please use a smaller photo.", "error")
                return redirect(url_for("detect"))
            probe.verify()
            f.stream.seek(0)
            img = Image.open(f.stream)
            img.load()
            img = img.convert("RGB")
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
            flash("That file is not a valid JPG/PNG image.", "error")
            return redirect(url_for("detect"))
        if min(img.size) < 100:
            flash("Image is too small (minimum 100×100 pixels). Please take a clearer photo.", "error")
            return redirect(url_for("detect"))

        fname = uuid.uuid4().hex + ".jpg"  # re-encoded: strips metadata, random name
        img.save(os.path.join(app.config["UPLOAD_FOLDER"], fname), "JPEG", quality=90)

        predictor = get_predictor(app.config)
        pred = predictor.predict(img)
        uncertain = pred["confidence"] < app.config["CONFIDENCE_THRESHOLD"]
        db.session.add(DiseasePrediction(
            predicted_class=pred["label"], confidence_score=pred["confidence"],
            model_version="demo-stub" if pred["demo"] else app.config["MODEL_VERSION"],
            is_uncertain=uncertain))
        db.session.commit()

        advisory = None if uncertain else DiseaseAdvisory.query.filter_by(disease_class=pred["label"]).first()
        names = {a.disease_class: a.display_name for a in DiseaseAdvisory.query.all()}
        for t in pred["top3"]:
            t["name"] = names.get(t["label"], t["label"].replace("_", " "))
        return render_template("result.html", pred=pred, uncertain=uncertain, advisory=advisory,
                               image=fname, threshold=app.config["CONFIDENCE_THRESHOLD"],
                               name=names.get(pred["label"], pred["label"].replace("_", " ")),
                               load_error=predictor.load_error)

    # ------------------------------------------------------------------ Module 4a: market prices
    @app.route("/market")
    def market():
        a = request.args
        if is_due(app):
            kick(app)

        # Base filter: turmeric only, strictly exclude invented SAMPLE rows
        base_genuine = MarketPrice.query.filter(
            func.lower(MarketPrice.commodity).like("%turmeric%"),
            ~MarketPrice.source_name.like("SAMPLE%"),
        )

        selected_state = (a.get("state") or "").strip()
        selected_district = (a.get("district") or "").strip()
        selected_market = (a.get("market") or "").strip()
        selected_variety = (a.get("variety") or "").strip()
        d_from = parse_date(a.get("from"))
        d_to = parse_date(a.get("to"))
        sort_by = (a.get("sort") or "date").strip().lower()
        sort_dir = (a.get("dir") or "desc").strip().lower()
        page = request.args.get("page", 1, type=int)
        per_page_raw = (request.args.get("per_page") or "50").strip().lower()

        # Dynamic dropdown options based on dataset & selection
        db_states = [
            s[0] for s in base_genuine.with_entities(MarketPrice.state)
            .filter(MarketPrice.state.isnot(None), MarketPrice.state != "")
            .distinct().order_by(MarketPrice.state).all()
        ]

        q_dist = base_genuine.with_entities(MarketPrice.district).filter(
            MarketPrice.district.isnot(None), MarketPrice.district != ""
        )
        if selected_state:
            q_dist = q_dist.filter(MarketPrice.state == selected_state)
        districts = [d[0] for d in q_dist.distinct().order_by(MarketPrice.district).all()]

        q_mkt = base_genuine.with_entities(MarketPrice.market_name).filter(
            MarketPrice.market_name.isnot(None), MarketPrice.market_name != ""
        )
        if selected_state:
            q_mkt = q_mkt.filter(MarketPrice.state == selected_state)
        if selected_district:
            q_mkt = q_mkt.filter(MarketPrice.district == selected_district)
        markets = [m[0] for m in q_mkt.distinct().order_by(MarketPrice.market_name).all()]

        q_var = base_genuine.with_entities(MarketPrice.variety).filter(
            MarketPrice.variety.isnot(None), MarketPrice.variety != ""
        )
        if selected_state:
            q_var = q_var.filter(MarketPrice.state == selected_state)
        if selected_district:
            q_var = q_var.filter(MarketPrice.district == selected_district)
        varieties = [v[0] for v in q_var.distinct().order_by(MarketPrice.variety).all()]

        # Hierarchy for instant client-side dropdown cascade
        hierarchy = {}
        all_pairs = base_genuine.with_entities(
            MarketPrice.state, MarketPrice.district, MarketPrice.market_name
        ).distinct().all()
        for st, dt, mk in all_pairs:
            if not st:
                continue
            hierarchy.setdefault(st, {})
            if dt:
                hierarchy[st].setdefault(dt, [])
                if mk and mk not in hierarchy[st][dt]:
                    hierarchy[st][dt].append(mk)

        # Apply user filters
        q = base_genuine
        if selected_state:
            q = q.filter(MarketPrice.state == selected_state)
        if selected_district:
            q = q.filter(MarketPrice.district == selected_district)
        if selected_market:
            q = q.filter(MarketPrice.market_name == selected_market)
        if selected_variety:
            q = q.filter(MarketPrice.variety == selected_variety)
        if d_from:
            q = q.filter(MarketPrice.reporting_date >= d_from)
        if d_to:
            q = q.filter(MarketPrice.reporting_date <= d_to)

        # Totals for dataset & matching results
        match_total = q.count()
        match_states = q.with_entities(MarketPrice.state).filter(
            MarketPrice.state.isnot(None), MarketPrice.state != ""
        ).distinct().count()
        match_districts = q.with_entities(MarketPrice.district).filter(
            MarketPrice.district.isnot(None), MarketPrice.district != ""
        ).distinct().count()
        match_markets = q.with_entities(MarketPrice.market_name).filter(
            MarketPrice.market_name.isnot(None), MarketPrice.market_name != ""
        ).distinct().count()

        db_total_records = base_genuine.count()
        db_total_states = len(db_states)
        db_total_districts = base_genuine.with_entities(MarketPrice.district).filter(
            MarketPrice.district.isnot(None), MarketPrice.district != ""
        ).distinct().count()
        db_total_markets = base_genuine.with_entities(MarketPrice.market_name).filter(
            MarketPrice.market_name.isnot(None), MarketPrice.market_name != ""
        ).distinct().count()

        # Sorting
        if sort_by == "price":
            col_order = MarketPrice.modal_price.desc() if sort_dir == "desc" else MarketPrice.modal_price.asc()
        elif sort_by == "market":
            col_order = MarketPrice.market_name.asc() if sort_dir == "asc" else MarketPrice.market_name.desc()
        elif sort_by == "district":
            col_order = MarketPrice.district.asc() if sort_dir == "asc" else MarketPrice.district.desc()
        elif sort_by == "state":
            col_order = MarketPrice.state.asc() if sort_dir == "asc" else MarketPrice.state.desc()
        else:
            sort_by = "date"
            col_order = MarketPrice.reporting_date.desc() if sort_dir == "desc" else MarketPrice.reporting_date.asc()

        q_ordered = q.order_by(col_order, MarketPrice.reporting_date.desc(), MarketPrice.market_name)

        # Pagination
        if per_page_raw == "all":
            rows = q_ordered.all()
            per_page = match_total or 1
            page = 1
            total_pages = 1
        else:
            try:
                per_page = int(per_page_raw)
                if per_page not in (25, 50, 100, 200):
                    per_page = 50
            except ValueError:
                per_page = 50
            page = max(1, page)
            total_pages = max(1, (match_total + per_page - 1) // per_page)
            if page > total_pages:
                page = total_pages
            offset = (page - 1) * per_page
            rows = q_ordered.offset(offset).limit(per_page).all()

        pagination = {
            "page": page,
            "per_page": per_page_raw,
            "total": match_total,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            "prev_page": page - 1,
            "next_page": page + 1,
        }

        # Date recency
        latest = base_genuine.with_entities(func.max(MarketPrice.reporting_date)).scalar()
        age = (date.today() - latest).days if latest else None

        # Check whether only sample data exists in DB
        only_sample = (
            MarketPrice.query.filter(
                func.lower(MarketPrice.commodity).like("%turmeric%"),
                MarketPrice.source_name.like("SAMPLE%"),
            ).count() > 0
            and not latest
        )

        # Chart: modal price over time for top 5 markets in current filter
        chart_rows = q.order_by(MarketPrice.reporting_date.desc()).limit(300).all()
        series, counts = {}, {}
        for r in chart_rows:
            if r.modal_price is None or r.reporting_date is None:
                continue
            series.setdefault(r.market_name, {})[r.reporting_date.isoformat()] = r.modal_price
            counts[r.market_name] = counts.get(r.market_name, 0) + 1
        top = sorted(counts, key=counts.get, reverse=True)[:5]
        labels = sorted({d for m in top for d in series[m]})
        chart = {"labels": labels,
                 "datasets": [{"label": m, "data": [series[m].get(d) for d in labels]} for m in top]}

        last_sync = AuditLog.query.filter_by(action="mandi_sync").order_by(AuditLog.created_at.desc()).first()
        is_partial_sync = bool(last_sync and "partial" in (last_sync.detail or "").lower())

        flags = {}
        if rows:
            for fl in PriceFlag.query.filter(PriceFlag.price_id.in_([r.price_id for r in rows])).all():
                flags.setdefault(fl.price_id, []).append(fl.reason)
        lang = a.get("lang") if a.get("lang") in ("en", "mr", "hi") else "en"
        my_alerts = (PriceAlert.query.filter_by(user_id=g.user.user_id, active=True).all()
                     if g.user and g.user.role in ("farmer", "buyer") else [])

        return render_template(
            "market.html", flags=flags, msum=market_summary(lang), lang=lang, my_alerts=my_alerts,
            industry=verified_industry_prices(), last_sync=last_sync, is_partial_sync=is_partial_sync,
            rows=rows, chart=chart,
            latest=latest, age=age, stale_days=STALE_DAYS,
            is_sample=False,
            only_sample=only_sample,
            opts={"state": db_states, "district": districts, "market": markets, "variety": varieties},
            hierarchy=hierarchy,
            counts={
                "match_total": match_total,
                "match_states": match_states,
                "match_districts": match_districts,
                "match_markets": match_markets,
                "db_total_records": db_total_records,
                "db_total_states": db_total_states,
                "db_total_districts": db_total_districts,
                "db_total_markets": db_total_markets,
            },
            pagination=pagination,
            sort={"by": sort_by, "dir": sort_dir},
            f=a,
            rec_result=None, rec_form=None)

    # ------------------------------------------------------------------ Module 4b: listings + enquiries
    @app.route("/listings")
    def listings():
        a = request.args
        q = ProductListing.query.filter_by(listing_status="open")
        if a.get("form") in PRODUCT_FORMS:
            q = q.filter_by(product_form=a["form"])
        if a.get("location", "").strip():
            q = q.filter(ProductListing.location.ilike("%" + a["location"].strip()[:60] + "%"))
        rows = q.order_by(ProductListing.created_at.desc()).limit(100).all()
        return render_template("listings.html", rows=rows, f=a, forms=PRODUCT_FORMS)

    @app.route("/listings/new", methods=["GET", "POST"])
    @login_required(roles=["farmer"])
    @verified_required
    def listing_new():
        if request.method == "POST":
            f = request.form
            errors, qty, price = [], None, None
            try:
                qty, price = float(f.get("quantity", "")), float(f.get("expected_price", ""))
            except ValueError:
                errors.append("Quantity and expected price must be numbers.")
            if qty is not None and not 0 < qty <= 1_000_000:
                errors.append("Quantity must be greater than 0.")
            if price is not None and not 0 < price <= 10_000_000:
                errors.append("Expected price must be greater than 0.")
            if f.get("product_form") not in PRODUCT_FORMS:
                errors.append("Choose a product form.")
            if f.get("quantity_unit") not in QTY_UNITS or f.get("price_unit") not in PRICE_UNITS:
                errors.append("Choose valid units.")
            if not 3 <= len(f.get("location", "").strip()) <= 120:
                errors.append("Enter the location (village / district).")
            avail = parse_date(f.get("availability_date")) if f.get("availability_date") else None
            if f.get("availability_date") and not avail:
                errors.append("Availability date is not valid.")
            qvals, qerrs = parse_quality(f)
            errors += qerrs
            if errors:
                for e in errors:
                    flash(e, "error")
                return render_template("listing_form.html", form=f, forms=PRODUCT_FORMS,
                                       qty_units=QTY_UNITS, price_units=PRICE_UNITS), 400
            lot = ProductListing(
                farmer_id=g.user.user_id, product_form=f["product_form"], quantity=qty,
                quantity_unit=f["quantity_unit"], quality_details=f.get("quality_details", "").strip()[:300] or None,
                expected_price=price, price_unit=f["price_unit"], location=f["location"].strip(),
                availability_date=avail)
            db.session.add(lot)
            db.session.flush()
            save_quality(lot.listing_id, qvals)
            audit("lot_created", "listing", lot.listing_id, f"{lot.product_form} {lot.quantity:g} {lot.quantity_unit}")
            db.session.commit()
            on_new_lot(lot.listing_id)      # AI agent searches open demands in the background
            flash("Listing published. The AI is looking for matching buyers; see AI Matches shortly.", "ok")
            return redirect(url_for("my_listings"))
        return render_template("listing_form.html", form={}, forms=PRODUCT_FORMS,
                               qty_units=QTY_UNITS, price_units=PRICE_UNITS)

    @app.route("/listings/<int:lid>")
    def listing_detail(lid):
        l = db.get_or_404(ProductListing, lid)
        already = bool(g.user and g.user.role == "buyer" and BuyerEnquiry.query.filter_by(
            listing_id=lid, buyer_id=g.user.user_id, enquiry_status="new").first())
        return render_template("listing_detail.html", l=l, already=already)

    @app.route("/listings/<int:lid>/enquire", methods=["POST"])
    @login_required(roles=["buyer"])
    def enquire(lid):
        l = db.get_or_404(ProductListing, lid)
        msg = request.form.get("enquiry_message", "").strip()
        if l.listing_status != "open":
            flash("This listing is closed.", "error")
        elif not 10 <= len(msg) <= 500:
            flash("Write an enquiry of 10–500 characters.", "error")
        elif BuyerEnquiry.query.filter_by(listing_id=lid, buyer_id=g.user.user_id, enquiry_status="new").first():
            flash("You already have an open enquiry on this listing.", "warn")
        else:
            db.session.add(BuyerEnquiry(listing_id=lid, buyer_id=g.user.user_id, enquiry_message=msg))
            db.session.commit()
            flash("Enquiry sent. The farmer will contact you if interested. "
                  "HaldiSetu does not guarantee a sale.", "ok")
        return redirect(url_for("listing_detail", lid=lid))

    @app.route("/my/listings")
    @login_required(roles=["farmer"])
    def my_listings():
        rows = ProductListing.query.filter_by(farmer_id=g.user.user_id).order_by(
            ProductListing.created_at.desc()).all()
        return render_template("my_listings.html", rows=rows)

    @app.route("/listings/<int:lid>/status", methods=["POST"])
    @login_required(roles=["farmer"])
    def listing_status(lid):
        l = db.get_or_404(ProductListing, lid)
        if l.farmer_id != g.user.user_id:
            abort(403)
        l.listing_status = "closed" if l.listing_status == "open" else "open"
        db.session.commit()
        return redirect(url_for("my_listings"))

    @app.route("/my/enquiries")
    @login_required(roles=["farmer", "buyer"])
    def my_enquiries():
        if g.user.role == "farmer":
            rows = (BuyerEnquiry.query.join(ProductListing)
                    .filter(ProductListing.farmer_id == g.user.user_id)
                    .order_by(BuyerEnquiry.created_at.desc()).all())
        else:
            rows = (BuyerEnquiry.query.filter_by(buyer_id=g.user.user_id)
                    .order_by(BuyerEnquiry.created_at.desc()).all())
        return render_template("my_enquiries.html", rows=rows)

    @app.route("/enquiries/<int:eid>/status", methods=["POST"])
    @login_required(roles=["farmer"])
    def enquiry_status(eid):
        e = db.get_or_404(BuyerEnquiry, eid)
        if e.listing.farmer_id != g.user.user_id:
            abort(403)
        new = request.form.get("status")
        if new not in ("new", "contacted", "closed"):
            abort(400)
        e.enquiry_status = new
        db.session.commit()
        return redirect(url_for("my_enquiries"))

    # ------------------------------------------------------------------ admin
    @app.route("/admin")
    @login_required(roles=["admin"])
    def admin():
        by_class = db.session.query(DiseasePrediction.predicted_class, func.count()).group_by(
            DiseasePrediction.predicted_class).all()
        total = DiseasePrediction.query.count()
        uncertain = DiseasePrediction.query.filter_by(is_uncertain=True).count()
        return render_template(
            "admin.html", total=total, uncertain=uncertain, by_class=by_class,
            advisories=DiseaseAdvisory.query.all(), schemes=Scheme.query.all(),
            n_prices=MarketPrice.query.count(), n_users=User.query.count(),
            latest=db.session.query(func.max(MarketPrice.reporting_date)).scalar())

    @app.route("/admin/import-prices", methods=["POST"])
    @login_required(roles=["admin"])
    def admin_import_prices():
        f, src = request.files.get("csv_file"), request.form.get("source_name", "").strip()
        if not f or not f.filename.lower().endswith(".csv") or len(src) < 5:
            flash("Choose a .csv file and describe its source (e.g. 'Agmarknet, downloaded 30 Oct 2026').", "error")
            return redirect(url_for("admin"))
        try:
            stats = import_csv_text(f.read().decode("utf-8-sig"), src[:200])
        except UnicodeDecodeError:
            flash("CSV must be UTF-8 encoded.", "error")
            return redirect(url_for("admin"))
        res = run_pipeline()          # market agent: flag odd records, fire price alerts (audited)
        audit("price_csv_import", "market_prices", None, f"{stats} | flagged {res['flagged']}, alerts {res['alerts']}")
        db.session.commit()
        flash(f"Import finished: {stats}. Market agent: {res['flagged']} record(s) flagged, {res['alerts']} alert(s) sent.", "ok")
        return redirect(url_for("admin"))

    # ------------------------------------------------------------------ errors
    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    def http_error(e):
        return render_template("error.html", e=e), e.code

    @app.errorhandler(413)
    def too_large(e):
        flash("That file is larger than the 5 MB limit.", "error")
        return redirect(url_for("detect"))

    return app

from agent_triggers import init_scheduler


def register_agent_module(app):
    # Register blueprint only once
    if agent_bp.name not in app.blueprints:
        app.register_blueprint(agent_bp)

    # Create tables after the app and database are initialized
    with app.app_context():
        db.create_all()

    return app


if __name__ == "__main__":
    app = create_app()

    # Register the agent module on the Flask app
    app = register_agent_module(app)

    # Start scheduler once
    init_scheduler(app)

    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1",
            use_reloader=False)