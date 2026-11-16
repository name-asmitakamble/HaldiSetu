"""End-to-end tests. Run from project root:  python -m unittest discover -s tests -v"""
import io
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

import seed  # noqa: E402
from app import create_app  # noqa: E402
from models import DiseasePrediction, ProductListing, BuyerEnquiry, MarketPrice, User  # noqa: E402
from models_market import UserProof  # noqa: E402
from scheme_engine import evaluate  # noqa: E402


def jpg_bytes(color=(40, 140, 60), size=(300, 300)):
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, "JPEG")
    b.seek(0)
    return b


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = create_app({
            "TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///" + os.path.join(self.tmp, "t.db"),
            "UPLOAD_FOLDER": os.path.join(self.tmp, "up"), "SECRET_KEY": "test",
            "MODEL_PATH": os.path.join(self.tmp, "no_model.keras"),
        })
        with self.app.app_context():
            self.admin = seed.run(sample_prices=True)
        self.c = self.app.test_client()

    def token(self, path="/login/farmer"):
        html = self.c.get(path).get_data(as_text=True)
        return re.search(r'name="_csrf" value="([^"]+)"', html).group(1)

    def post(self, path, data=None, form_page="/login/farmer", **kw):
        data = dict(data or {})
        data["_csrf"] = self.token(form_page)
        return self.c.post(path, data=data, **kw)

    def register_login(self, phone, role, name="Test User", verify=True):
        self.post(f"/register/{role}", {"name": name, "phone": phone, "password": "password123"}, f"/register/{role}")
        if verify:
            with self.app.app_context():
                u = User.query.filter_by(phone=phone).first()
                from models import db
                db.session.add(UserProof(user_id=u.user_id, doc_type="test", status="approved"))
                db.session.commit()
        with self.app.app_context():
            _role = User.query.filter_by(phone=phone).first().role
        return self.post(f"/login/{_role}", {"phone": phone, "password": "password123"}, f"/login/{_role}", follow_redirects=True)


class TestFlows(Base):
    def test_pages_load(self):
        for p in ("/", "/detect", "/schemes", "/market", "/listings", "/login", "/register", "/login/farmer", "/login/buyer", "/register/farmer", "/register/buyer", "/marketplace", "/demands", "/tools/fresh-vs-dried"):
            self.assertEqual(self.c.get(p).status_code, 200, p)

    def test_csrf_enforced(self):
        self.assertEqual(self.c.post("/login/farmer", data={"phone": "1", "password": "x"}).status_code, 400)

    def test_register_validation_and_login(self):
        r = self.post("/register/farmer", {"name": "A", "phone": "123", "password": "short"}, "/register/farmer")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.c.get("/register/admin").status_code, 404)  # cannot self-register as admin
        # a role field smuggled into the form is ignored: the URL decides the role
        self.post("/register/buyer", {"name": "Sneaky", "phone": "9876500000", "role": "admin", "password": "password123"}, "/register/buyer")
        with self.app.app_context():
            self.assertEqual(User.query.filter_by(phone="9876500000").first().role, "buyer")
        r = self.register_login("9876543210", "farmer", "Ravi Patil")
        self.assertIn("Welcome, Ravi Patil", r.get_data(as_text=True))
        self.assertEqual(self.post("/login/farmer", {"phone": "9876543210", "password": "bad"}, "/login/farmer").status_code, 401)

    def test_separate_farmer_and_buyer_logins(self):
        self.register_login("9876543211", "farmer", "Sita Farmer")
        self.post("/logout", form_page="/")
        self.register_login("9876543212", "buyer", "Mill Buyer")
        self.post("/logout", form_page="/")
        r = self.post("/login/buyer", {"phone": "9876543211", "password": "password123"}, "/login/buyer")
        self.assertEqual(r.status_code, 401)
        self.assertIn("Farmer login", r.get_data(as_text=True))
        r = self.post("/login/farmer", {"phone": "9876543212", "password": "password123"}, "/login/farmer")
        self.assertEqual(r.status_code, 401)
        self.assertIn("Buyer login", r.get_data(as_text=True))
        self.post("/login/farmer", {"phone": "9876543211", "password": "password123"}, "/login/farmer")
        self.assertEqual(self.c.get("/listings/new").status_code, 200)
        self.assertEqual(self.c.get("/demands/new").status_code, 403)

    def test_admin_login_button_and_create_new_admin(self):
        for page in ("/", "/login"):
            self.assertIn("Admin login", self.c.get(page).get_data(as_text=True))
        phone, pw = self.admin
        self.post("/login/admin", {"phone": phone, "password": pw}, "/login/admin")
        self.assertEqual(self.c.get("/admin/admins").status_code, 200)
        bad = self.post("/admin/admins", {"name": "Second", "phone": "9000000077", "password": "password123",
                                          "password2": "different"}, "/admin/admins")
        self.assertEqual(bad.status_code, 400)
        self.post("/admin/admins", {"name": "Second Admin", "phone": "9000000077", "password": "password123",
                                    "password2": "password123"}, "/admin/admins")
        self.post("/logout", form_page="/")
        r = self.post("/login/admin", {"phone": "9000000077", "password": "password123"}, "/login/admin", follow_redirects=True)
        self.assertIn("Welcome, Second Admin", r.get_data(as_text=True))
        # a farmer can never open the page
        self.post("/logout", form_page="/")
        self.register_login("9876543299", "farmer", "Plain Farmer")
        self.assertEqual(self.c.get("/admin/admins").status_code, 403)

    def test_login_redirect_goes_to_chooser(self):
        page = self.c.get("/listings/new", follow_redirects=True).get_data(as_text=True)
        self.assertIn("Farmer login", page)
        self.assertIn("Buyer login", page)

    def test_detect_demo_flow_and_logging(self):
        t = self.token("/detect")
        r = self.c.post("/detect", data={"_csrf": t, "leaf_image": (jpg_bytes(), "leaf.jpg")},
                        content_type="multipart/form-data")
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("DEMO MODE", html)
        self.assertIn("Model confidence", html)
        with self.app.app_context():
            p = DiseasePrediction.query.one()
            self.assertEqual(p.model_version, "demo-stub")

    def test_detect_rejects_bad_files(self):
        t = self.token("/detect")
        for name, content in (("x.jpg", io.BytesIO(b"not an image")), ("x.txt", jpg_bytes()), ("x.png", io.BytesIO(b""))):
            r = self.c.post("/detect", data={"_csrf": t, "leaf_image": (content, name)},
                            content_type="multipart/form-data", follow_redirects=True)
            self.assertIn("alert", r.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(DiseasePrediction.query.count(), 0)
        tiny = self.c.post("/detect", data={"_csrf": t, "leaf_image": (jpg_bytes(size=(40, 40)), "t.jpg")},
                           content_type="multipart/form-data", follow_redirects=True)
        self.assertIn("too small", tiny.get_data(as_text=True))

    def test_uncertain_hides_advisory(self):
        self.app.config["CONFIDENCE_THRESHOLD"] = 0.9999
        t = self.token("/detect")
        html = self.c.post("/detect", data={"_csrf": t, "leaf_image": (jpg_bytes(), "l.jpg")},
                           content_type="multipart/form-data").get_data(as_text=True)
        self.assertIn("Uncertain prediction", html)
        self.assertNotIn("Treatment guidance", html)

    def test_schemes_agent_languages(self):
        self.register_login("9000000010", "farmer", "Scheme Farmer")
        r = self.post("/schemes/profile", {"state": "Maharashtra", "owns_land": "yes", "farmer_type": "owner", "land_ha": "1.2",
                                           "stage": "pre_sowing", "language": "mr", "docs": ["aadhaar", "bank"]},
                      "/schemes", follow_redirects=True)
        html = r.get_data(as_text=True)
        self.assertIn("पीएम-किसान सन्मान निधी", html)           # Marathi scheme name
        self.assertIn("तुमचे कृती-कॅलेंडर", html)               # Marathi calendar heading
        self.assertIn("official", html.lower())
        hi = self.c.get("/schemes?lang=hi").get_data(as_text=True)
        self.assertIn("आवेदन कैसे करें", hi)
        en = self.c.get("/schemes?lang=en").get_data(as_text=True)
        self.assertIn("Documents you have: 2 of 4", en)          # PM-KISAN needs 4, farmer ticked 2
        self.assertIn("Fits your current stage", en)             # PMFBY is relevant before planting

    def test_schemes_not_eligible_tenant(self):
        self.register_login("9000000011", "farmer")
        self.post("/schemes/profile", {"state": "Kerala", "owns_land": "no", "farmer_type": "tenant", "stage": "harvest", "language": "en"}, "/schemes")
        html = self.c.get("/schemes").get_data(as_text=True)
        self.assertIn("Does not match your answers", html)       # PM-KISAN needs land ownership

    def test_schemes_public_view(self):
        self.assertIn("PM-KISAN", self.c.get("/schemes?lang=en").get_data(as_text=True))

    def test_scheme_engine_rules(self):
        prof = {"state": "Kerala", "land_ha": 3.0, "owns_land": "yes", "farmer_type": "owner"}
        self.assertEqual(evaluate({"max_land_ha": 2}, prof)[0], "no")
        self.assertEqual(evaluate({"states": ["Kerala"], "max_land_ha": 5}, prof)[0], "match")
        self.assertEqual(evaluate({"states": ["Assam"]}, prof)[0], "no")
        self.assertEqual(evaluate({"max_land_ha": 2}, dict(prof, land_ha=None))[0], "unknown")

    def test_market_sample_banner_and_filters(self):
        html = self.c.get("/market").get_data(as_text=True)
        self.assertIn("SAMPLE DATA", html)
        self.assertNotIn("live", html.lower().replace("deliver", ""))  # never claim "live" prices
        html = self.c.get("/market?market=Sangli").get_data(as_text=True)
        self.assertIn("Sangli", html)
        self.assertNotIn(">Erode<", html.split("<table>")[-1])

    def test_listing_and_enquiry_flow(self):
        self.register_login("9000000001", "farmer", "Farmer One")
        r = self.post("/listings/new", {"product_form": "Dried turmeric (finger)", "quantity": "25", "quantity_unit": "Quintal",
                                         "expected_price": "11500", "price_unit": "Rs/Quintal", "location": "Sangli, Maharashtra"},
                      "/listings/new", follow_redirects=True)
        self.assertIn("Listing published", r.get_data(as_text=True))
        bad = self.post("/listings/new", {"product_form": "x", "quantity": "-1", "expected_price": "0"}, "/listings/new")
        self.assertEqual(bad.status_code, 400)
        self.post("/logout", form_page="/")
        self.assertEqual(self.c.get("/listings/new").status_code, 302)

        self.register_login("9000000002", "buyer", "Buyer One")
        self.assertEqual(self.c.get("/listings/new").status_code, 403)
        page = self.c.get("/listings/1").get_data(as_text=True)
        self.assertNotIn("9000000001", page)  # farmer phone not public
        r = self.post("/listings/1/enquire", {"enquiry_message": "Need 10 quintals, please share quality."},
                      "/listings/1", follow_redirects=True)
        self.assertIn("Enquiry sent", r.get_data(as_text=True))
        r = self.post("/listings/1/enquire", {"enquiry_message": "Duplicate enquiry attempt here."},
                      "/listings/1", follow_redirects=True)
        self.assertIn("already have an open enquiry", r.get_data(as_text=True))
        self.post("/logout", form_page="/")

        self.post("/login/farmer", {"phone": "9000000001", "password": "password123"}, "/login/farmer")
        page = self.c.get("/my/enquiries").get_data(as_text=True)
        self.assertIn("9000000002", page)  # farmer sees buyer contact
        self.post("/enquiries/1/status", {"status": "contacted"}, "/my/enquiries")
        with self.app.app_context():
            self.assertEqual(BuyerEnquiry.query.one().enquiry_status, "contacted")
        self.post("/listings/1/status", form_page="/my/listings")
        with self.app.app_context():
            self.assertEqual(ProductListing.query.one().listing_status, "closed")

    def test_admin_import_prices(self):
        phone, pw = self.admin
        self.post("/login/admin", {"phone": phone, "password": pw}, "/login/admin")
        csv_text = ("State,District,Market,Commodity,Variety,Arrival_Date,Min_Price,Max_Price,Modal_Price\n"
                    "Maharashtra,Hingoli,Hingoli,Turmeric,Finger,2026-10-28,11000,12500,11800\n"
                    "Maharashtra,Hingoli,Hingoli,Turmeric,Finger,2026-10-28,11000,12500,11800\n"
                    "Maharashtra,Pune,Pune,Onion,Local,2026-10-28,1000,2000,1500\n"
                    "Maharashtra,Pune,Pune,Turmeric,Finger,bad-date,1,2,3\n")
        t = self.token("/admin")
        r = self.c.post("/admin/import-prices", follow_redirects=True, content_type="multipart/form-data",
                        data={"_csrf": t, "source_name": "Test source file", "csv_file": (io.BytesIO(csv_text.encode()), "p.csv")})
        self.assertIn("added&#39;: 1", r.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(MarketPrice.query.filter_by(market_name="Hingoli").count(), 1)

    def test_admin_requires_admin(self):
        self.assertEqual(self.c.get("/admin").status_code, 302)
        self.register_login("9000000003", "farmer")
        self.assertEqual(self.c.get("/admin").status_code, 403)


if __name__ == "__main__":
    unittest.main()
