"""
Unit tests for Industry Price Agent and Sell-Channel Advisor Agent.
Run: python -m unittest tests/test_sell_channel_advisor.py
"""
import os
import re
import tempfile
import unittest

from app import create_app
import seed
from channel_advisor import evaluate_lot_channels, _generate_multilingual_reasons, _polish_advisor_text
from industry_agent import analyze_industry, get_all_industry_stats, refresh_industry_stats
from market_agent import run_pipeline
from models import ProductListing, User, db
from models_market import BuyerDemand, AuditLog, LotQuality


class TestSellChannelAdvisor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///" + os.path.join(self.tmp, "test_advisor.db"),
            "UPLOAD_FOLDER": os.path.join(self.tmp, "up"),
            "PROOF_FOLDER": os.path.join(self.tmp, "proofs"),
            "SECRET_KEY": "test-key",
            "MODEL_PATH": os.path.join(self.tmp, "none.keras"),
        })
        with self.app.app_context():
            seed.run(sample_prices=True, demo_marketplace=True)
        self.c = self.app.test_client()

    def token(self, path="/login/farmer"):
        return re.search(r'name="_csrf" value="([^"]+)"', self.c.get(path).get_data(as_text=True)).group(1)

    def post(self, path, data=None, page="/login/farmer", **kw):
        d = dict(data or {})
        d["_csrf"] = self.token(page)
        return self.c.post(path, data=d, **kw)

    def login_farmer(self, phone="9222222201", pw="DemoPass123"):
        self.c = self.app.test_client()
        with self.app.app_context():
            _role = User.query.filter_by(phone=phone).first().role
        return self.post(f"/login/{_role}", {"phone": phone, "password": pw}, f"/login/{_role}", follow_redirects=True)

    def test_industry_agent_stats(self):
        with self.app.app_context():
            stats = get_all_industry_stats()
            self.assertEqual(len(stats), 4)

            # Check Medicine sector (seeded with NutraPharma demo: 13,200/q, curcumin >= 4.0%, moisture <= 10%, lab=True)
            med = next(s for s in stats if s["industry"] == "Medicine / nutraceutical maker")
            self.assertEqual(med["n_offers"], 1)
            self.assertEqual(med["avg_price"], 13200.0)
            self.assertEqual(med["requirements"]["curcumin_min_typical"], 4.0)
            self.assertEqual(med["requirements"]["moisture_max_typical"], 10.0)
            self.assertEqual(med["requirements"]["lab_required_count"], 1)
            self.assertTrue(med["confidence"]["is_demo_only"])
            self.assertIn("test buyer", med["confidence"]["badge"].lower())

            # Check Food sector (seeded with Spice Foods demo: 11,800/q, moisture <= 12%)
            food = next(s for s in stats if s["industry"] == "Food & spice company")
            self.assertEqual(food["avg_price"], 11800.0)
            self.assertEqual(food["requirements"]["moisture_max_typical"], 12.0)
            self.assertEqual(food["requirements"]["lab_required_count"], 0)

            # Test refresh_industry_stats hook
            summary = refresh_industry_stats()
            self.assertEqual(len(summary), 4)
            self.assertTrue(all("industry" in x and "offers" in x for x in summary))

    def test_sell_channel_advisor_evaluation(self):
        with self.app.app_context():
            # Lot 1 has 6q finger, moisture 9%, curcumin 4.6%, lab report present
            lot1 = ProductListing.query.get(1)
            res = evaluate_lot_channels(lot1, lang="en")

            # Must evaluate Mandi and all 4 industries
            self.assertEqual(res["mandi"]["channel_type"], "mandi")
            self.assertEqual(len(res["industries"]), 4)

            # Lot 1 qualifies for Medicine (curcumin 4.6% >= 4.0%, moisture 9% <= 10%, has lab report)
            med_channel = next(c for c in res["industries"] if c["industry_type"] == "Medicine / nutraceutical maker")
            self.assertEqual(med_channel["status"], "qualified")
            self.assertEqual(med_channel["expected_price"], 13200.0)

            # Lot 1 should be recommended Medicine because ₹13,200/q > Mandi baseline (~₹11,000/q)
            rec = res["recommendation"]
            self.assertIn("Medicine", rec["target_name"])
            self.assertEqual(rec["price"], 13200.0)
            self.assertGreater(rec["gain_per_q"], 0)
            self.assertIn("Medicine", rec["reason"])
            self.assertIn("13,200", rec["reason"])

            # Test multilingual reason generation
            en, mr, hi = _generate_multilingual_reasons(lot1, res["mandi"], rec)
            self.assertIn("Medicine", en)
            self.assertIn("13,200", en)
            self.assertIn("13,200", mr)
            self.assertIn("13,200", hi)

    def test_unlockable_advisor_scenario(self):
        with self.app.app_context():
            # Lot with moisture within limits (9.5%), but no curcumin tested and no lab report
            lot2 = ProductListing.query.get(2)
            lot2.quality.moisture_pct = 9.5
            db.session.commit()

            res = evaluate_lot_channels(lot2, lang="en")

            # Medicine requires curcumin and lab report, so with moisture ok, it is unlockable
            med_channel = next(c for c in res["industries"] if c["industry_type"] == "Medicine / nutraceutical maker")
            self.assertEqual(med_channel["status"], "unlockable")
            self.assertTrue(len(med_channel["unlock_actions"]) > 0)

            # Recommendation should mention how to unlock
            rec = res["recommendation"]
            self.assertEqual(rec["mode"], "unlockable")
            self.assertTrue(len(rec["unlock_action"]) > 0)

    def test_ai_polishing_number_safety(self):
        # Even if LLM runs, it must NEVER alter numbers
        original = "Offers ₹13,200/quintal, giving ₹13,200 extra on 6 quintals."
        # If text is unchanged, it returns original
        res_text, changed = _polish_advisor_text(original, "en")
        self.assertEqual(set(re.findall(r"\d+", original)), set(re.findall(r"\d+", res_text)))

    def test_where_to_sell_page(self):
        self.login_farmer()

        # Access default where-to-sell page
        r = self.c.get("/where-to-sell")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)

        self.assertIn("Where Should I Sell?", html)
        self.assertIn("Recommended Route", html)
        self.assertIn("Channel-by-Channel Comparison", html)
        self.assertIn("Connect & Draft Offer", html)
        self.assertIn("Local Mandi (APMC Auction)", html)
        self.assertIn("Medicine", html)

        # Access specific lot where-to-sell page
        r2 = self.c.get("/lots/1/where-to-sell?lang=mr")
        self.assertEqual(r2.status_code, 200)
        html2 = r2.get_data(as_text=True)
        self.assertIn("शिफारस", html2)

    def test_orchestrator_pipeline_step(self):
        with self.app.app_context():
            res = run_pipeline()
            self.assertIn("industry_stats", res)
            self.assertEqual(len(res["industry_stats"]), 4)

            # Audit log must record the industry stats refresh
            log = AuditLog.query.filter_by(action="agent_industry_stats").first()
            self.assertIsNotNone(log)
            self.assertIn("4 sector(s) refreshed", log.detail)


if __name__ == "__main__":
    unittest.main()
