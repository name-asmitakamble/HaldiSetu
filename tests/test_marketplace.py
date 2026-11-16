"""Marketplace, deals/bill, price engine, verification, dashboards, mandi sync. Run: python -m unittest discover -s tests -v"""
import io
import os
import re
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image

import mandi_sync
import seed
from app import create_app
from matching import evaluate, group_suggestion
from models import MarketPrice, ProductListing, User, db
from models_market import (AuditLog, BuyerDemand, Deal, DemandResponse,
                           LotQuality, UserProof)
from price_engine import (fresh_vs_dried, industry_prices, price_card,
                          sell_when)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///" + os.path.join(self.tmp, "t.db"),
            "UPLOAD_FOLDER": os.path.join(self.tmp, "up"),
            "PROOF_FOLDER": os.path.join(self.tmp, "proofs"),
            "SECRET_KEY": "t",
            "MODEL_PATH": os.path.join(self.tmp, "none.keras"),
        })
        with self.app.app_context():
            self.admin = seed.run(sample_prices=True, demo_marketplace=True)
        self.c = self.app.test_client()

    def token(self, path="/login/farmer"):
        return re.search(r'name="_csrf" value="([^"]+)"', self.c.get(path).get_data(as_text=True)).group(1)

    def post(self, path, data=None, page="/login/farmer", **kw):
        d = dict(data) if data else {}
        d["_csrf"] = self.token(page)
        return self.c.post(path, data=d, **kw)

    def login(self, phone, pw="DemoPass123"):
        self.c = self.app.test_client()
        with self.app.app_context():
            _role = User.query.filter_by(phone=phone).first().role
        return self.post(f"/login/{_role}", {"phone": phone, "password": pw}, f"/login/{_role}", follow_redirects=True)

    def uid(self, phone):
        with self.app.app_context():
            return User.query.filter_by(phone=phone).first().user_id


class TestMatching(Base):
    def test_explanation_unlocks_lab_report(self):
        with self.app.app_context():
            pharma = BuyerDemand.query.filter_by(min_curcumin=4.0, max_moisture=10).first()
            lot_nolab = ProductListing.query.filter_by(quantity=4).first()
            ev = evaluate(lot_nolab, pharma)
            self.assertIn("moisture", ev["fail_keys"] | {"moisture"})
            self.assertIn("quantity", ev["fail_keys"])
            self.assertIn("lab report", ev["explanation"].lower())
            lot_good = ProductListing.query.filter_by(quantity=6).first()
            ev2 = evaluate(lot_good, pharma)
            self.assertEqual(ev2["checks"][[c["key"] for c in ev2["checks"]].index("curcumin")]["status"], "pass")

    def test_self_declared_curcumin_is_a_gap(self):
        with self.app.app_context():
            pharma = BuyerDemand.query.filter_by(min_curcumin=4.0).first()
            lot = ProductListing.query.filter_by(quantity=6).first()
            lot.quality.has_lab_report = False
            ev = evaluate(lot, pharma)
            cur = [c for c in ev["checks"] if c["key"] == "curcumin"][0]
            self.assertEqual(cur["status"], "gap")

    def test_group_suggestion(self):
        with self.app.app_context():
            food = BuyerDemand.query.filter_by(industry_type="Food & spice company").first()
            g = group_suggestion(food, ProductListing.query.filter_by(listing_status="open").all())
            self.assertIsNotNone(g)
            self.assertGreaterEqual(g["total_q"], 8)
            self.assertEqual(len(g["lots"]), 2)


class TestPrice(Base):
    def test_price_card_uses_data_and_flags_sample(self):
        with self.app.app_context():
            lot = ProductListing.query.filter_by(quantity=6).first()
            from matching import direct_offers, rank_demands_for_lot
            ranked = rank_demands_for_lot(lot, BuyerDemand.query.filter_by(status="open").all())
            card = price_card(lot, direct_offers(ranked))
            self.assertTrue(card["base"]["is_sample"])
            self.assertIn("NOT applied", " ".join(card["notes"]))
            self.assertIsNotNone(card["best_offer"])
            self.assertAlmostEqual(card["gap"], card["best_offer"] - card["base"]["modal"])
            self.assertGreaterEqual(card["base"]["modal"], card["floor"])

    def test_sell_when_and_math(self):
        with self.app.app_context():
            sw = sell_when(["Sangli"], storage_cost=100)
            self.assertGreaterEqual(sw["n_days"], 5)
            self.assertIn("storage cost", sw["verdict"])
            r = fresh_vs_dried(10, 4000, 12000, 5, 300)
            self.assertAlmostEqual(r["dried_rev"], 2 * 12000)
            self.assertAlmostEqual(r["net_dried"], 24000 - 3000)
            self.assertAlmostEqual(r["diff"], 21000 - 40000)
            self.assertAlmostEqual(r["breakeven_dried_price"], (40000 + 3000) / 2)

    def test_industry_board_labels_test_buyers(self):
        with self.app.app_context():
            board = {r["industry"]: r for r in industry_prices()}
            self.assertEqual(board["Medicine / nutraceutical maker"]["n"], 1)
            self.assertEqual(board["Medicine / nutraceutical maker"]["demo_n"], 1)
        html = self.c.get("/market").get_data(as_text=True)
        self.assertIn("not official market prices", html)

    def test_calculator_page(self):
        html = self.c.get("/tools/fresh-vs-dried?fresh_q=10&fresh_price=4000&dried_price=12000&ratio=5&cost=300").get_data(as_text=True)
        self.assertIn("Difference (dried", html)


class TestWorkflow(Base):
    def test_full_deal_flow_and_bill(self):
        self.login("9222222201")
        page = self.c.get("/lots/1").get_data(as_text=True)
        self.assertIn("Adjusted estimate", page)
        self.assertIn("SAMPLE DATA", page)
        pharma_id = 2
        r = self.post(f"/demands/{pharma_id}/respond", {"listing_id": 1, "ask_price": "12500"}, f"/demands/{pharma_id}", follow_redirects=True)
        self.assertIn("Your lot was sent", r.get_data(as_text=True))
        dup = self.post(f"/demands/{pharma_id}/respond", {"listing_id": 1}, f"/demands/{pharma_id}", follow_redirects=True)
        self.assertIn("already offered", dup.get_data(as_text=True))

        self.login("9111111102")
        r = self.c.get(f"/demands/{pharma_id}").get_data(as_text=True)
        self.assertIn("Propose deal", r)
        r = self.post("/responses/1/deal", {"quantity_q": "6", "price_per_q": "12500"}, f"/demands/{pharma_id}", follow_redirects=True)
        self.assertIn("Deal proposed", r.get_data(as_text=True))

        with self.app.app_context():
            d = Deal.query.one()
            self.assertEqual(d.total, 75000)
            self.assertTrue(d.bill_no.startswith("HS-"))

        bad = self.c.get("/deals/1/bill")
        self.assertNotIn("HS-", bad.get_data(as_text=True))
        self.assertEqual(bad.status_code, 302)

        self.login("9222222201")
        self.post("/deals/1/action", {"action": "confirm"}, "/deals/1")
        with self.app.app_context():
            self.assertEqual(ProductListing.query.get(1).listing_status, "closed")

        self.post("/deals/1/action", {"action": "delivered"}, "/deals/1")

        self.login("9111111102")
        bad = self.post("/deals/1/action", {"action": "paid", "payment_ref": ""}, "/deals/1", follow_redirects=True)
        self.assertIn("payment reference", bad.get_data(as_text=True))
        self.post("/deals/1/action", {"action": "paid", "payment_ref": "UTR123"}, "/deals/1")

        self.login("9222222201")
        self.post("/deals/1/action", {"action": "settled"}, "/deals/1")

        bill = self.c.get("/deals/1/bill").get_data(as_text=True)
        self.assertIn("not a GST/tax invoice", bill)
        self.assertIn("75,000.00", bill)
        self.assertIn("confirmed received by the farmer", bill)

        with self.app.app_context():
            self.assertEqual(Deal.query.one().status, "settled")
            actions = {a.action for a in AuditLog.query.all()}
            self.assertTrue({'deal_proposed', 'deal_settled', 'deal_paid', 'lot_offered', 'deal_confirm'} <= actions)

    def test_cancel_after_confirm_restores_quantity(self):
        self.login("9222222201")
        self.post("/demands/2/respond", {"listing_id": 1}, "/demands/2")
        self.login("9111111102")
        self.post("/responses/1/deal", {"quantity_q": "2", "price_per_q": "12000"}, "/demands/2")
        self.login("9222222201")
        self.post("/deals/1/action", {"action": "confirm"}, "/deals/1")
        with self.app.app_context():
            self.assertAlmostEqual(ProductListing.query.get(1).quantity, 4.0)
        self.post("/deals/1/action", {"action": "cancel"}, "/deals/1")
        with self.app.app_context():
            self.assertAlmostEqual(ProductListing.query.get(1).quantity, 6.0)

    def test_deal_validation_and_access(self):
        self.login("9222222201")
        self.post("/demands/2/respond", {"listing_id": 1}, "/demands/2")
        self.login("9111111102")
        r = self.post("/responses/1/deal", {"quantity_q": "99", "price_per_q": "12000"}, "/demands/2", follow_redirects=True)
        self.assertIn("more than the farmer", r.get_data(as_text=True))
        self.login("9111111101")
        self.assertEqual(self.post("/responses/1/deal", {"quantity_q": "1", "price_per_q": "1"}, "/demands/1").status_code, 403)
        self.login("9111111102")
        self.post("/responses/1/deal", {"quantity_q": "2", "price_per_q": "12000"}, "/demands/2")
        self.login("9111111101")
        self.assertEqual(self.c.get("/deals/1").status_code, 403)

    def test_unverified_user_blocked(self):
        self.c = self.app.test_client()
        self.post("/register/farmer", {"name": "New Farmer", "phone": "9333333301", "password": "password123"}, "/register/farmer")
        self.login("9333333301", "password123")
        r = self.c.get("/listings/new", follow_redirects=True)
        self.assertIn("must be verified", r.get_data(as_text=True))
        dash = self.c.get("/dashboard").get_data(as_text=True)
        self.assertIn("Farmer dashboard", dash)

    def test_quality_card_edit_changes_match(self):
        self.login("9222222201")
        before = self.c.get("/lots/2").get_data(as_text=True)
        self.assertIn("lab report showing curcumin", before)
        r = self.post("/lots/2/quality", {
            "variety": "Finger",
            "moisture_pct": "9",
            "curcumin_pct": "4.4",
            "has_lab_report": "on",
            "lab_report_ref": "DemoLab/2026/200"
        }, "/lots/2/quality", follow_redirects=True)
        self.assertIn("Quality card saved", r.get_data(as_text=True))
        bad = self.post("/lots/2/quality", {"moisture_pct": "abc"}, "/lots/2/quality")
        self.assertEqual(bad.status_code, 400)
        with self.app.app_context():
            self.assertEqual(LotQuality.query.filter_by(listing_id=2).one().curcumin_pct, 4.4)

    def test_lot_dashboard_owner_only(self):
        self.login("9111111101")
        self.assertEqual(self.c.get("/lots/1").status_code, 403)


class TestDashboardsAdmin(Base):
    def test_three_dashboards(self):
        self.login("9222222201")
        self.assertIn("Farmer dashboard", self.c.get("/dashboard").get_data(as_text=True))
        self.login("9111111101")
        self.assertIn("Buyer dashboard", self.c.get("/dashboard").get_data(as_text=True))
        phone, pw = self.admin
        self.login(phone, pw)
        self.assertIn("Admin dashboard", self.c.get("/dashboard").get_data(as_text=True))
        for p in ("/admin/verifications", "/admin/users", "/admin/audit", "/admin/schemes", "/admin/schemes/1", "/admin"):
            self.assertEqual(self.c.get(p).status_code, 200)
        self.login("9222222201")
        for p in ("/admin/users", "/admin/verifications", "/admin/schemes"):
            self.assertEqual(self.c.get(p).status_code, 403)

    def test_proof_upload_and_admin_approval(self):
        self.c = self.app.test_client()
        self.post("/register/farmer", {"name": "Proof Farmer", "phone": "9333333302", "password": "password123"}, "/register/farmer")
        self.login("9333333302", "password123")
        buf = io.BytesIO()
        Image.new("RGB", (200, 200), (200, 200, 200)).save(buf, "PNG")
        buf.seek(0)
        t = self.token("/verification")
        r = self.c.post("/verification", data={
            "_csrf": t,
            "doc_type": "Land record (7/12 or 8A)",
            "proof": (buf, "land.png")
        }, content_type="multipart/form-data", follow_redirects=True)
        self.assertIn("Proof uploaded", r.get_data(as_text=True))

        evil = self.c.post("/verification", data={
            "_csrf": self.token("/verification"),
            "doc_type": "Land record (7/12 or 8A)",
            "proof": (io.BytesIO(b"<script>"), "x.png")
        }, content_type="multipart/form-data", follow_redirects=True)
        self.assertIn("not a valid image", evil.get_data(as_text=True))

        with self.app.app_context():
            pid = UserProof.query.filter_by(doc_type="Land record (7/12 or 8A)").one().proof_id

        self.assertEqual(self.c.get(f"/admin/proof/{pid}").status_code, 403)
        phone, pw = self.admin
        self.login(phone, pw)
        self.assertEqual(self.c.get(f"/admin/proof/{pid}").status_code, 200)
        self.post(f"/admin/verifications/{pid}/review", {
            "decision": "approved",
            "admin_note": "matches 7/12"
        }, "/admin/verifications")

        self.login("9333333302", "password123")
        self.assertEqual(self.c.get("/listings/new").status_code, 200)

    def test_admin_edits_scheme(self):
        phone, pw = self.admin
        self.login(phone, pw)
        r = self.post("/admin/schemes/1", {
            "scheme_name": "PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)",
            "description": "d",
            "eligibility_text": "e",
            "benefits": "b",
            "official_url": "https://pmkisan.gov.in/",
            "last_verified_date": "2026-10-31",
            "eligibility_rules": '{"owns_land": true}',
            "name_en": "PM-KISAN",
            "hl_en": "Updated text",
            "steps_en": "a\nb",
            "stages": ["harvest"],
            "docs": ["aadhaar"]
        }, "/admin/schemes/1", follow_redirects=True)
        self.assertIn("Scheme saved", r.get_data(as_text=True))
        bad = self.post("/admin/schemes/1", {
            "scheme_name": "x",
            "official_url": "http://insecure",
            "eligibility_rules": "[1]"
        }, "/admin/schemes/1")
        self.assertIn("must start with https", bad.get_data(as_text=True))


class FakeResp:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeHttp:
    def __init__(self, records=None, boom=False):
        self.records = records if records is not None else []
        self.boom = boom

    def get(self, url, params=None, timeout=None):
        if self.boom:
            raise RuntimeError("network down")
        return FakeResp({"records": self.records, "total": len(self.records)})


class TestMandiSync(Base):
    def test_sync_parses_api_records(self):
        recs = [{
            "state": "Maharashtra",
            "district": "Sangli",
            "market": "Sangli",
            "commodity": "Turmeric",
            "variety": "Rajapuri",
            "arrival_date": (date.today() - timedelta(days=1)).strftime("%d/%m/%Y"),
            "min_price": "11000",
            "max_price": "14000",
            "modal_price": "12500"
        }]
        with self.app.app_context():
            ok, msg, stats = mandi_sync.sync(api_key="k", http=FakeHttp(recs))
            self.assertTrue(ok)
            self.assertEqual(stats["added"], 1)
            row = MarketPrice.query.filter_by(market_name="Sangli", variety="Rajapuri", reporting_date=date.today() - timedelta(days=1)).first()
            self.assertEqual(row.modal_price, 12500)
            self.assertEqual(row.commodity, "Turmeric")

    def test_sync_failure_is_safe(self):
        with self.app.app_context():
            n = MarketPrice.query.count()
        ok, msg, _ = mandi_sync.sync(api_key="k", http=FakeHttp(boom=True))
        self.assertFalse(ok)
        self.assertIn("Could not reach", msg)
        with self.app.app_context():
            self.assertEqual(MarketPrice.query.count(), n)
        ok, msg, _ = mandi_sync.sync(api_key="", http=FakeHttp())
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
