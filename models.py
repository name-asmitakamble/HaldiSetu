from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"
    user_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # farmer / buyer / admin
    district = db.Column(db.String(80))
    phone = db.Column(db.String(15), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class DiseaseAdvisory(db.Model):
    __tablename__ = "disease_advisories"
    advisory_id = db.Column(db.Integer, primary_key=True)
    disease_class = db.Column(db.String(80), unique=True, nullable=False)
    display_name = db.Column(db.String(120), nullable=False)
    symptoms = db.Column(db.Text, nullable=False)
    prevention_guidance = db.Column(db.Text, nullable=False)
    treatment_guidance = db.Column(db.Text, nullable=False)
    source_name = db.Column(db.String(200), nullable=False)
    source_url = db.Column(db.String(300), nullable=False)
    last_verified_date = db.Column(db.Date)


class DiseasePrediction(db.Model):
    __tablename__ = "disease_predictions"
    prediction_id = db.Column(db.Integer, primary_key=True)
    predicted_class = db.Column(db.String(80))
    confidence_score = db.Column(db.Float)
    model_version = db.Column(db.String(50))
    is_uncertain = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Scheme(db.Model):
    __tablename__ = "schemes"
    scheme_id = db.Column(db.Integer, primary_key=True)
    scheme_name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    eligibility_text = db.Column(db.Text, nullable=False)
    eligibility_rules = db.Column(db.Text, nullable=False)  # JSON string
    benefits = db.Column(db.Text, nullable=False)
    required_documents = db.Column(db.Text)
    official_url = db.Column(db.String(300), nullable=False)
    last_verified_date = db.Column(db.Date)


class MarketPrice(db.Model):
    __tablename__ = "market_prices"
    price_id = db.Column(db.Integer, primary_key=True)
    commodity = db.Column(db.String(50), default="Turmeric")
    state = db.Column(db.String(60))
    district = db.Column(db.String(60))
    market_name = db.Column(db.String(100))
    variety = db.Column(db.String(60))
    reporting_date = db.Column(db.Date, index=True)
    minimum_price = db.Column(db.Float)
    maximum_price = db.Column(db.Float)
    modal_price = db.Column(db.Float)
    unit = db.Column(db.String(30), default="Rs/Quintal")
    source_name = db.Column(db.String(200))
    imported_at = db.Column(db.DateTime, default=datetime.utcnow)


class ProductListing(db.Model):
    __tablename__ = "product_listings"
    listing_id = db.Column(db.Integer, primary_key=True)
    farmer_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    product_form = db.Column(db.String(40), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    quantity_unit = db.Column(db.String(20), nullable=False)
    quality_details = db.Column(db.String(300))
    expected_price = db.Column(db.Float, nullable=False)
    price_unit = db.Column(db.String(30), nullable=False)
    location = db.Column(db.String(120), nullable=False)
    availability_date = db.Column(db.Date)
    listing_status = db.Column(db.String(20), default="open")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    farmer = db.relationship("User", backref="listings")


class BuyerEnquiry(db.Model):
    __tablename__ = "buyer_enquiries"
    enquiry_id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("product_listings.listing_id"), nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    enquiry_message = db.Column(db.String(500), nullable=False)
    enquiry_status = db.Column(db.String(20), default="new")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    listing = db.relationship("ProductListing", backref="enquiries")
    buyer = db.relationship("User")
