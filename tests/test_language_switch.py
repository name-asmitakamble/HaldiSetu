"""
Test for website-wide language switching across Dashboard and pages.
Run: python -m unittest tests/test_language_switch.py
"""
import os
import re
import tempfile
import unittest

from app import create_app
import seed
from models import User
from models_market import FarmerProfile


class TestLanguageSwitch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///" + os.path.join(self.tmp, "test_lang.db"),
            "UPLOAD_FOLDER": os.path.join(self.tmp, "up"),
            "PROOF_FOLDER": os.path.join(self.tmp, "proofs"),
            "SECRET_KEY": "test-lang-key",
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
        with self.app.app_context():
            _role = User.query.filter_by(phone=phone).first().role
        return self.post(f"/login/{_role}", {"phone": phone, "password": pw}, f"/login/{_role}", follow_redirects=True)

    def test_language_switch_flow(self):
        self.login_farmer()

        # 1. Default dashboard is English
        r_en = self.c.get("/dashboard")
        self.assertEqual(r_en.status_code, 200)
        html_en = r_en.get_data(as_text=True)
        self.assertIn("Namaste", html_en)
        self.assertIn("Farmer dashboard", html_en)
        self.assertIn("Disease check", html_en)
        self.assertIn("Market prices", html_en)

        # 2. Select Marathi via /set-language/mr
        r_set_mr = self.c.get("/set-language/mr", follow_redirects=True)
        self.assertEqual(r_set_mr.status_code, 200)
        html_mr = r_set_mr.get_data(as_text=True)

        # Dashboard elements are in Marathi
        self.assertIn("नमस्कार", html_mr)
        self.assertIn("शेतकरी डॅशबोर्ड", html_mr)
        self.assertIn("रोग तपासणी", html_mr)
        self.assertIn("शासकीय योजना", html_mr)
        self.assertIn("बाजारपेठ", html_mr)
        self.assertIn("बाजार भाव", html_mr)
        self.assertIn("मी कुठे विक्री करावी?", html_mr)

        # 3. Visit another page (/where-to-sell) -> still in Marathi!
        r_wts = self.c.get("/where-to-sell")
        self.assertEqual(r_wts.status_code, 200)
        html_wts = r_wts.get_data(as_text=True)
        self.assertIn("रोग तपासणी", html_wts)
        self.assertIn("शासकीय योजना", html_wts)
        self.assertIn("बाजार भाव", html_wts)

        # 4. Select Hindi via /set-language/hi
        r_set_hi = self.c.get("/set-language/hi", follow_redirects=True)
        self.assertEqual(r_set_hi.status_code, 200)
        html_hi = r_set_hi.get_data(as_text=True)

        # Dashboard elements are in Hindi
        self.assertIn("नमस्ते", html_hi)
        self.assertIn("किसान डैशबोर्ड", html_hi)
        self.assertIn("रोग जांच", html_hi)
        self.assertIn("सरकारी योजनाएं", html_hi)
        self.assertIn("मंडी भाव", html_hi)
        self.assertIn("मैं कहाँ बेचूँ?", html_hi)

        # 5. Switch back to English via /set-language/en
        r_set_en = self.c.get("/set-language/en", follow_redirects=True)
        self.assertEqual(r_set_en.status_code, 200)
        html_back = r_set_en.get_data(as_text=True)
        self.assertIn("Namaste", html_back)
        self.assertIn("Farmer dashboard", html_back)
        self.assertIn("Disease check", html_back)


if __name__ == "__main__":
    unittest.main()
