"""Tables for the Direct Farmer-to-Industry Marketplace (demand posts, quality cards, responses)."""
from datetime import datetime

from models import db

INDUSTRIES = ["Food & spice company", "Medicine / nutraceutical maker",
              "Cosmetics / natural-dye maker", "Research lab / extract maker"]


class LotQuality(db.Model):
    """The 'quality card' of a farmer's lot. All values are DECLARED by the farmer unless a lab report exists."""
    __tablename__ = "lot_quality"
    quality_id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("product_listings.listing_id"), unique=True, nullable=False)
    variety = db.Column(db.String(60))
    moisture_pct = db.Column(db.Float)
    curcumin_pct = db.Column(db.Float)
    has_lab_report = db.Column(db.Boolean, default=False)
    lab_report_ref = db.Column(db.String(120))
    polished = db.Column(db.Boolean, default=False)
    harvest_date = db.Column(db.Date)
    listing = db.relationship("ProductListing", backref=db.backref("quality", uselist=False))


class BuyerDemand(db.Model):
    """An industry buyer's requirement: 'we need X quintal, curcumin >= Y, moisture <= Z, delivery at P by D'."""
    __tablename__ = "buyer_demands"
    demand_id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    industry_type = db.Column(db.String(40), nullable=False)
    product_form = db.Column(db.String(40), nullable=False)       # a listing form or "Any form"
    quantity = db.Column(db.Float, nullable=False)
    quantity_unit = db.Column(db.String(20), nullable=False)
    delivery_location = db.Column(db.String(120), nullable=False)
    deliver_by = db.Column(db.Date)
    offered_price = db.Column(db.Float, nullable=False)
    price_unit = db.Column(db.String(30), nullable=False)
    min_curcumin = db.Column(db.Float)
    max_moisture = db.Column(db.Float)
    requires_lab_report = db.Column(db.Boolean, default=False)
    notes = db.Column(db.String(300))
    is_demo = db.Column(db.Boolean, default=False)                # clearly-labelled TEST buyer
    status = db.Column(db.String(20), default="open")             # open / closed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    buyer = db.relationship("User")


class DemandResponse(db.Model):
    """A farmer offering a specific lot against a demand."""
    __tablename__ = "demand_responses"
    __table_args__ = (db.UniqueConstraint("demand_id", "listing_id", name="uq_demand_lot"),)
    response_id = db.Column(db.Integer, primary_key=True)
    demand_id = db.Column(db.Integer, db.ForeignKey("buyer_demands.demand_id"), nullable=False)
    listing_id = db.Column(db.Integer, db.ForeignKey("product_listings.listing_id"), nullable=False)
    farmer_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    ask_price = db.Column(db.Float)                               # Rs/quintal, optional
    message = db.Column(db.String(300))
    match_score = db.Column(db.Float)
    status = db.Column(db.String(20), default="sent")             # sent / shortlisted / declined
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    demand = db.relationship("BuyerDemand", backref="responses")
    listing = db.relationship("ProductListing")
    farmer = db.relationship("User")


# ---------------------------------------------------------------- extension tables (dashboards, schemes agent, deals)
class FarmerProfile(db.Model):
    """Minimum data the scheme agent needs. No ID numbers are stored — documents are a yes/no checklist."""
    __tablename__ = "farmer_profiles"
    profile_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), unique=True, nullable=False)
    state = db.Column(db.String(60))
    district = db.Column(db.String(60))
    land_ha = db.Column(db.Float)
    owns_land = db.Column(db.String(5))            # yes / no
    farmer_type = db.Column(db.String(20))         # owner / tenant / sharecropper
    stage = db.Column(db.String(20))               # pre_sowing .. selling
    docs = db.Column(db.Text, default="[]")        # JSON list of document keys the farmer HAS
    language = db.Column(db.String(5), default="en")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SchemeInfo(db.Model):
    """Multilingual content + stage/document metadata for a Scheme row (kept separate from models.py)."""
    __tablename__ = "scheme_info"
    info_id = db.Column(db.Integer, primary_key=True)
    scheme_id = db.Column(db.Integer, db.ForeignKey("schemes.scheme_id"), unique=True, nullable=False)
    stages = db.Column(db.Text, default="[]")          # JSON list of stage keys
    required_docs = db.Column(db.Text, default="[]")   # JSON list of document keys
    names = db.Column(db.Text, default="{}")           # JSON {lang: name}
    highlights = db.Column(db.Text, default="{}")      # JSON {lang: text}
    steps = db.Column(db.Text, default="{}")           # JSON {lang: [step, ...]}


class UserProof(db.Model):
    """Verification proof (land record / business licence). Admin approves; AI never verifies alone."""
    __tablename__ = "user_proofs"
    proof_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    doc_type = db.Column(db.String(60), nullable=False)
    filename = db.Column(db.String(100))               # random name inside private_uploads/ (None for demo accounts)
    status = db.Column(db.String(20), default="pending")   # pending / approved / rejected
    admin_note = db.Column(db.String(200))
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User", foreign_keys=[user_id])


class Deal(db.Model):
    """Agreed sale between a farmer's lot and a buyer's demand. HaldiSetu does NOT process payment."""
    __tablename__ = "deals"
    deal_id = db.Column(db.Integer, primary_key=True)
    response_id = db.Column(db.Integer, db.ForeignKey("demand_responses.response_id"), unique=True, nullable=False)
    demand_id = db.Column(db.Integer, db.ForeignKey("buyer_demands.demand_id"), nullable=False)
    listing_id = db.Column(db.Integer, db.ForeignKey("product_listings.listing_id"), nullable=False)
    farmer_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    quantity_q = db.Column(db.Float, nullable=False)
    price_per_q = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default="proposed")  # proposed/confirmed/delivered/paid/settled/cancelled
    payment_ref = db.Column(db.String(60))
    bill_no = db.Column(db.String(30), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    response = db.relationship("DemandResponse", backref=db.backref("deal", uselist=False))
    demand = db.relationship("BuyerDemand")
    listing = db.relationship("ProductListing")
    farmer = db.relationship("User", foreign_keys=[farmer_id])
    buyer = db.relationship("User", foreign_keys=[buyer_id])


class AuditLog(db.Model):
    """Every important action is saved here (project plan: 'every action is saved in an audit log')."""
    __tablename__ = "audit_log"
    log_id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    action = db.Column(db.String(60), nullable=False)
    entity = db.Column(db.String(40))
    entity_id = db.Column(db.Integer)
    detail = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    actor = db.relationship("User")


# ---------------------------------------------------------------- agent layer tables (market agent, proof agent)
class PriceFlag(db.Model):
    """Market agent: a mandi record that looks odd. The record is kept and shown with a warning — never deleted."""
    __tablename__ = "price_flags"
    __table_args__ = (db.UniqueConstraint("price_id", "code", name="uq_price_flag"),)
    flag_id = db.Column(db.Integer, primary_key=True)
    price_id = db.Column(db.Integer, db.ForeignKey("market_prices.price_id"), nullable=False, index=True)
    code = db.Column(db.String(20), nullable=False)        # range / jump
    reason = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PriceAlert(db.Model):
    """Farmer's price alert: tell me when <market or highest market> modal price goes above/below X Rs/quintal."""
    __tablename__ = "price_alerts"
    alert_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False, index=True)
    market_name = db.Column(db.String(100))                # None = highest market of the day
    direction = db.Column(db.String(5), nullable=False)    # above / below
    threshold_q = db.Column(db.Float, nullable=False)
    active = db.Column(db.Boolean, default=True)
    last_triggered_on = db.Column(db.Date)                 # data date it last fired for (one alert per data date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Notification(db.Model):
    """In-app notification (price alerts). SMS / e-mail delivery is NOT implemented."""
    __tablename__ = "notifications"
    notif_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False, index=True)
    text = db.Column(db.String(300), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ProofAnalysis(db.Model):
    """Proof agent's reading of an uploaded document."""
    __tablename__ = "proof_analyses"

    analysis_id = db.Column(db.Integer, primary_key=True)
    proof_id = db.Column(
        db.Integer,
        db.ForeignKey("user_proofs.proof_id"),
        unique=True,
        nullable=False
    )
    extracted_name = db.Column(db.String(120))
    extracted_type = db.Column(db.String(60))
    flags = db.Column(db.Text, default="[]")
    mode = db.Column(db.String(10), default="basic")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    proof = db.relationship(
        "UserProof",
        backref=db.backref("analysis", uselist=False)
    )

    @property
    def flag_list(self):
        import json

        try:
            return json.loads(self.flags or "[]")
        except ValueError:
            return []


# ------------------------------------------------------------------
# Compatibility aliases for Marketplace AI agents
# ------------------------------------------------------------------

from models import ProductListing

Lot = ProductListing
Requirement = BuyerDemand