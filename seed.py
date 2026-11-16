"""
Seed the database:  python seed.py [--sample-prices] [--demo-marketplace]

* Creates the admin account (ADMIN_PHONE / ADMIN_PASSWORD from .env; random password printed once if unset)
* Loads advisory + scheme records (idempotent: re-running updates, never duplicates)
* --demo-marketplace adds clearly-labelled TEST buyers (+ one demo farmer with 3 lots), password DemoPass123
* --sample-prices adds DEMO market rows labelled "SAMPLE DATA" (for screenshots/testing only —
  replace with a real import for the final demo: see README, step "Real market data")

IMPORTANT — DATA HONESTY
  last_verified_date is left EMPTY on purpose. After you (and Member 1) check each record against
  its official page, set the date in the dicts below and re-run this script. The UI shows
  "Not yet verified" until then. Do not fill in a date you did not actually check.
"""
import json
import os
import random
import secrets
import sys
from datetime import date, timedelta

from models import (DiseaseAdvisory, MarketPrice, ProductListing, Scheme, User, db)
from models_market import BuyerDemand, LotQuality, SchemeInfo, UserProof
from scheme_content import CONTENT
from more_schemes import SCHEMES_EXTRA
IPM_URL = "https://ppqs.gov.in/sites/default/files/ipm_pop-turmeric.pdf"
IPM_SRC = "Directorate of Plant Protection, Quarantine & Storage — IPM Package of Practices for Turmeric"
EXPERT = ("If symptoms are severe, spreading, or you are unsure, show the plant to your local Krishi Vigyan "
          "Kendra (KVK) or agriculture officer before applying any chemical.")

# Keys MUST match ml/class_labels.json (Member 1's class names).
ADVISORIES = [
    dict(disease_class="Healthy_Leaf", display_name="Healthy leaf",
         symptoms="No visible disease symptoms on the uploaded leaf. Leaf colour and surface look normal.",
         prevention_guidance="Use healthy, disease-free seed rhizomes. Keep the field well drained, avoid water-logging "
                             "and overcrowding, remove crop residue and weeds, and inspect leaves regularly.",
         treatment_guidance="No treatment is indicated by this image. Continue regular field scouting. " + EXPERT,
         source_name=IPM_SRC, source_url=IPM_URL),
    dict(disease_class="Leaf_Blotch", display_name="Leaf blotch",
         symptoms="Small brown/oval spots on both leaf surfaces that enlarge and merge into blotches, often with a "
                  "yellow halo; badly affected leaves look scorched and dry. Commonly reported in humid, wet weather. "
                  "May be confused with leaf spot or nutrient/water stress.",
         prevention_guidance="Plant healthy rhizomes with proper spacing, keep good drainage, collect and destroy "
                             "badly infected leaves, and avoid leaving infected residue in the field.",
         treatment_guidance="The IPM package for turmeric lists management measures including protective fungicide "
                            "sprays for leaf blotch. Check the exact product, dose and timing in the source document "
                            "before use. " + EXPERT,
         source_name=IPM_SRC, source_url=IPM_URL),
    dict(disease_class="Leaf_Spot", display_name="Leaf spot",
         symptoms="Brown spots with lighter (greyish/whitish) centres and a yellow margin, mainly on the upper leaf "
                  "surface; spots may merge and leaves dry from the tips. May be confused with leaf blotch.",
         prevention_guidance="Use disease-free seed rhizomes, avoid dense planting and water-logging, remove and "
                             "destroy infected leaves, and keep the field clean of residue.",
         treatment_guidance="The IPM package for turmeric lists management measures including fungicide sprays for "
                            "leaf spot. Check the exact product, dose and timing in the source document before use. "
                            + EXPERT,
         source_name=IPM_SRC, source_url=IPM_URL),
    dict(disease_class="Dry_Leaf", display_name="Dry leaf",
         symptoms="Leaf is dried or browned. This can be natural drying as the crop matures, water or heat stress, "
                  "or a late stage of a disease — an image alone cannot tell these apart.",
         prevention_guidance="Maintain even soil moisture and good drainage, avoid stress during the growing period, "
                             "and check younger leaves for spots to rule out disease.",
         treatment_guidance="No disease-specific treatment can be suggested from a dry leaf alone. If younger leaves "
                            "also show spots or blotches, upload those. " + EXPERT,
         source_name=IPM_SRC, source_url=IPM_URL),
]

VERIFY_NOTE = "Details as listed by the official portal; confirm current rules before applying."
SCHEMES = [
    dict(scheme_name="PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)",
         description="Central government income-support scheme for landholding farmer families.",
         eligibility_text="Landholding farmer families, subject to the scheme's exclusion criteria.",
         eligibility_rules={"owns_land": True, "note": VERIFY_NOTE},
         benefits="Income support paid in instalments directly to the bank account (check portal for the current amount).",
         required_documents="Land records, Aadhaar, bank account details (as listed on the portal).",
         official_url="https://pmkisan.gov.in/"),
    dict(scheme_name="PMFBY (Pradhan Mantri Fasal Bima Yojana)",
         description="Crop insurance against crop loss from natural causes.",
         eligibility_text="Farmers (including tenant farmers / sharecroppers) growing crops notified for the area and season. "
                          "Whether turmeric is notified depends on the state and season.",
         eligibility_rules={"farmer_types": ["owner", "tenant", "sharecropper"],
                            "note": "Check whether turmeric is notified in your district and season."},
         benefits="Insurance cover and compensation for notified crop losses, at subsidised premium.",
         required_documents="Land/tenancy records, bank account, sowing declaration (as listed on the portal).",
         official_url="https://pmfby.gov.in/"),
    dict(scheme_name="Kisan Credit Card (KCC)",
         description="Credit facility so farmers can meet crop-cultivation and related expenses.",
         eligibility_text="Farmers who own or cultivate land, including tenant farmers and sharecroppers; availed through banks.",
         eligibility_rules={"farmer_types": ["owner", "tenant", "sharecropper"], "note": VERIFY_NOTE},
         benefits="Short-term credit for cultivation at concessional interest through banks.",
         required_documents="Identity/address proof, land or tenancy details, bank forms (varies by bank).",
         official_url="https://www.myscheme.gov.in/"),
    dict(scheme_name="Agriculture Infrastructure Fund (AIF)",
         description="Financing for post-harvest management and community farming infrastructure, e.g. warehouses and primary processing.",
         eligibility_text="Farmers, FPOs, agri-entrepreneurs and others with a viable post-harvest project.",
         eligibility_rules={"note": "Requires a project proposal; useful for turmeric drying/polishing/storage units."},
         benefits="Medium/long-term loans with interest subvention for eligible infrastructure projects.",
         required_documents="Project report, identity and land/premises documents (as listed on the portal).",
         official_url="https://agriinfra.dac.gov.in/"),
    dict(scheme_name="PM-FME (PM Formalisation of Micro Food Processing Enterprises)",
         description="Support for micro food-processing units (e.g. turmeric boiling, polishing, powder making).",
         eligibility_text="Existing or new individual micro food-processing enterprises, FPOs, SHGs and cooperatives.",
         eligibility_rules={"note": "Applies to processing enterprises, not to growing turmeric alone."},
         benefits="Credit-linked subsidy for upgrading or setting up micro food-processing units.",
         required_documents="Identity proof, bank account, enterprise details (as listed on the portal).",
         official_url="https://pmfme.mofpi.gov.in/"),
]

SCHEMES = SCHEMES + SCHEMES_EXTRA

SAMPLE_MARKETS = [  # (state, district, market, variety, base modal Rs/quintal) — INVENTED demo numbers
    ("Maharashtra", "Sangli", "Sangli", "Finger", 11500),
    ("Telangana", "Nizamabad", "Nizamabad", "Bulb", 10800),
    ("Tamil Nadu", "Erode", "Erode", "Finger", 11900),
    ("Andhra Pradesh", "Guntur", "Duggirala", "Finger", 11200),
]


def seed_advisories():
    for d in ADVISORIES:
        row = DiseaseAdvisory.query.filter_by(disease_class=d["disease_class"]).first() or DiseaseAdvisory()
        for k, v in d.items():
            setattr(row, k, v)
        db.session.add(row)
    db.session.commit()


def seed_schemes():
    for d in SCHEMES:
        d = dict(d, eligibility_rules=json.dumps(d["eligibility_rules"]))
        row = Scheme.query.filter_by(scheme_name=d["scheme_name"]).first() or Scheme()
        for k, v in d.items():
            setattr(row, k, v)
        db.session.add(row)
    db.session.commit()


def seed_sample_prices(days=21):
    if MarketPrice.query.filter(MarketPrice.source_name.like("SAMPLE%")).count():
        return
    rnd = random.Random(42)
    for st, dist, mkt, var, base in SAMPLE_MARKETS:
        price = base
        for i in range(days, -1, -1):
            price = max(8000, price + rnd.randint(-120, 130))
            db.session.add(MarketPrice(
                commodity="Turmeric", state=st, district=dist, market_name=mkt, variety=var,
                reporting_date=date.today() - timedelta(days=i), minimum_price=price - 600,
                maximum_price=price + 700, modal_price=price, unit="Rs/Quintal",
                source_name="SAMPLE DATA (invented for demo — not a real market price)"))
    db.session.commit()


def ensure_admin():
    phone = os.getenv("ADMIN_PHONE", "9000000000")
    if User.query.filter_by(phone=phone).first():
        return None
    pw = os.getenv("ADMIN_PASSWORD") or secrets.token_urlsafe(9)
    u = User(name="Administrator", role="admin", phone=phone)
    u.set_password(pw)
    db.session.add(u)
    db.session.commit()
    return phone, pw


def seed_scheme_info():
    """Multilingual text, stages and documents for each scheme (see scheme_content.py)."""
    for name, c in CONTENT.items():
        sch = Scheme.query.filter_by(scheme_name=name).first()
        if not sch:
            continue
        info = SchemeInfo.query.filter_by(scheme_id=sch.scheme_id).first() or SchemeInfo(scheme_id=sch.scheme_id)
        info.stages, info.required_docs = json.dumps(c["stages"]), json.dumps(c["docs"])
        info.names, info.highlights = json.dumps(c["names"], ensure_ascii=False), json.dumps(c["highlights"], ensure_ascii=False)
        info.steps = json.dumps(c["steps"], ensure_ascii=False)
        db.session.add(info)
    db.session.commit()


DEMO_PASSWORD = "DemoPass123"   # demo accounts only — never use --demo-marketplace on a public server


def _demo_user(name, phone, role, district=None):
    u = User.query.filter_by(phone=phone).first()
    if not u:
        u = User(name=name, role=role, phone=phone, district=district)
        u.set_password(DEMO_PASSWORD)
        db.session.add(u)
        db.session.flush()
        db.session.add(UserProof(user_id=u.user_id, doc_type="Demo account (no document)", status="approved",
                                 admin_note="Seeded demo account"))
    return u


def seed_demo_marketplace():
    """CLEARLY LABELLED test buyers + one demo farmer, so the full workflow can be shown (project plan)."""
    if BuyerDemand.query.filter_by(is_demo=True).count():
        return
    today = date.today()
    buyers = [
        ("Test Buyer – Spice Foods (demo)", "9111111101", "Food & spice company", "Dried turmeric (finger)", 8, 11800, None, 12, False, "Sangli, Maharashtra", 40),
        ("Test Buyer – NutraPharma (demo)", "9111111102", "Medicine / nutraceutical maker", "Dried turmeric (finger)", 10, 13200, 4.0, 10, True, "Sangli, Maharashtra", 45),
        ("Test Buyer – NaturalDyes (demo)", "9111111103", "Cosmetics / natural-dye maker", "Any form", 6, 11100, None, None, False, "Kolhapur, Maharashtra", 30),
        ("Test Buyer – Extract Research Lab (demo)", "9111111104", "Research lab / extract maker", "Dried turmeric (finger)", 2, 14000, 5.0, 9, True, "Pune, Maharashtra", 35),
    ]
    for name, phone, industry, form, qty, price, curc, moist, lab, loc, days in buyers:
        b = _demo_user(name, phone, "buyer")
        db.session.add(BuyerDemand(buyer_id=b.user_id, industry_type=industry, product_form=form, quantity=qty, quantity_unit="Quintal",
                                   delivery_location=loc, deliver_by=today + timedelta(days=days), offered_price=price,
                                   price_unit="Rs/Quintal", min_curcumin=curc, max_moisture=moist, requires_lab_report=lab,
                                   notes="ILLUSTRATIVE demo requirement — not a real company's specification.", is_demo=True))
    f = _demo_user("Demo Farmer – Ravi Patil", "9222222201", "farmer", "Sangli")
    lots = [  # (form, qty, price, location, variety, moisture, curcumin, lab ref)
        ("Dried turmeric (finger)", 6, 11500, "Sangli, Maharashtra", "Finger", 9.0, 4.6, "DemoLab/2026/117"),
        ("Dried turmeric (finger)", 4, 11300, "Sangli, Maharashtra", "Finger", 10.5, None, None),
        ("Fresh rhizome", 20, 4200, "Walwa, Sangli", "Salem", None, None, None),
    ]
    for form, qty, price, loc, var, moist, curc, lab in lots:
        l = ProductListing(farmer_id=f.user_id, product_form=form, quantity=qty, quantity_unit="Quintal", expected_price=price,
                           price_unit="Rs/Quintal", location=loc, availability_date=today + timedelta(days=20))
        db.session.add(l)
        db.session.flush()
        db.session.add(LotQuality(listing_id=l.listing_id, variety=var, moisture_pct=moist, curcumin_pct=curc,
                                  has_lab_report=bool(lab), lab_report_ref=lab))
    db.session.commit()


def run(sample_prices=False, demo_marketplace=False):
    seed_advisories()
    seed_schemes()
    seed_scheme_info()
    if demo_marketplace:
        seed_demo_marketplace()
    if sample_prices:
        seed_sample_prices()
    return ensure_admin()


if __name__ == "__main__":
    from app import create_app

    with create_app().app_context():
        created = run(sample_prices="--sample-prices" in sys.argv, demo_marketplace="--demo-marketplace" in sys.argv)
        labels = json.load(open("ml/class_labels.json", encoding="utf-8"))
        missing = [c for c in labels if not DiseaseAdvisory.query.filter_by(disease_class=c).first()]
        print("Seed complete.")
        if created:
            print(f"Admin created -> phone: {created[0]}  password: {created[1]}  (save it now; shown once)")
        if missing:
            print("WARNING: no advisory for model classes:", missing, "-> add them in seed.py")
