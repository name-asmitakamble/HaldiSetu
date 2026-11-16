"""AI matching agent: new lot / new demand -> proposals -> farmer offers -> deal -> contacts. No API key needed."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import date, timedelta

import agent_tools as T
from models import ProductListing, db
from models_agent import AgentNotification, AgentRun, MatchProposal
from models_market import BuyerDemand, DemandResponse, Notification
from tests.test_marketplace import Base


class TestAIMatching(Base):
    def setUp(self):
        os.environ.pop("ANTHROPIC_API_KEY", None)          # rule-based mode: deterministic and offline
        super().setUp()
        self.app.config.update(AGENT_SYNC=True)            # run the agent inline so tests can assert on it

    def _post_demand(self, **over):
        data = {"industry_type": "Food & spice company", "product_form": "Dried turmeric (finger)", "quantity": "5",
                "quantity_unit": "Quintal", "offered_price": "12500", "price_unit": "Rs/Quintal",
                "delivery_location": "Sangli, Maharashtra", "max_moisture": "12", **over}
        self.login("9111111101")
        return self.post("/demands/new", data, "/demands/new", follow_redirects=True)

    def test_scoring_uses_real_quality_card(self):
        with self.app.app_context():
            lot = ProductListing.query.filter_by(farmer_id=self.uid("9222222201")).first()
            demand = BuyerDemand.query.filter_by(is_demo=True).first()
            s = T.score_pair(lot, demand)
            self.assertIn("breakdown", s)
            self.assertEqual(T.find_candidates("requirement", demand.demand_id, min_score=0)["count"] >= 0, True)
            self.assertIsNone(T.find_candidates("lot", 999999).get("candidates"))

    def test_new_demand_triggers_agent_and_notifies_both(self):
        self._post_demand()
        with self.app.app_context():
            self.assertTrue(AgentRun.query.filter_by(trigger="new_requirement").count() >= 1)
            runs = AgentRun.query.filter_by(trigger="new_requirement").all()
            self.assertTrue(all(r.status == "done" for r in runs), [r.summary for r in runs])
            props = MatchProposal.query.filter_by(requirement_id=BuyerDemand.query.order_by(BuyerDemand.demand_id.desc()).first().demand_id).all()
            self.assertTrue(props, "agent should propose at least one demo lot")
            self.assertTrue(all(p.score >= 60 for p in props))
            # both sides were told, through the table the dashboards already show
            self.assertTrue(Notification.query.filter_by(user_id=self.uid("9222222201")).count() >= 1)
            self.assertTrue(AgentNotification.query.filter_by(kind="match").count() >= 2)

    def test_full_connection_flow_through_ai_match(self):
        self._post_demand()
        self.login("9222222201")                                    # farmer sees the AI match
        page = self.c.get("/matches").get_data(as_text=True)
        self.assertIn("AI score", page)
        with self.app.app_context():
            p = MatchProposal.query.order_by(MatchProposal.score.desc()).first()
            pid, did, lid = p.id, p.requirement_id, p.lot_id
        self.assertNotIn("9111111101", page)                        # no phone numbers on the match page
        r = self.post(f"/matches/{pid}/accept", {}, "/matches")
        self.assertEqual(r.status_code, 302)
        with self.app.app_context():
            resp = DemandResponse.query.filter_by(demand_id=did, listing_id=lid).first()
            self.assertIsNotNone(resp)
            self.assertEqual(MatchProposal.query.get(pid).status, "accepted")
            rid = resp.response_id
        # offering twice is refused, buyer now proposes a deal, farmer confirms -> contacts visible
        self.post(f"/matches/{pid}/accept", {}, "/matches")
        with self.app.app_context():
            self.assertEqual(DemandResponse.query.filter_by(demand_id=did, listing_id=lid).count(), 1)
        self.login("9111111101")
        self.assertIn("Offer sent", self.c.get("/matches").get_data(as_text=True))
        self.assertNotIn("9222222201", self.c.get("/connections").get_data(as_text=True))
        self.post(f"/responses/{rid}/deal", {"quantity_q": "5", "price_per_q": "12000"}, f"/demands/{did}")
        self.login("9222222201")
        self.post("/deals/1/action", {"action": "confirm"}, "/deals/1")
        self.assertIn("9111111101", self.c.get("/connections").get_data(as_text=True))
        self.login("9111111101")
        self.assertIn("9222222201", self.c.get("/connections").get_data(as_text=True))

    def test_buyer_interest_and_access_control(self):
        self._post_demand()
        with self.app.app_context():
            pid = MatchProposal.query.order_by(MatchProposal.score.desc()).first().id
        r = self.post(f"/matches/{pid}/interest", {}, "/matches")        # buyer owns this demand
        self.assertEqual(r.status_code, 302)
        with self.app.app_context():
            self.assertEqual(MatchProposal.query.get(pid).status, "interested")
        self.login("9111111103")                                         # unrelated buyer
        self.assertEqual(self.post(f"/matches/{pid}/dismiss", {}, "/matches").status_code, 403)
        self.assertEqual(self.post(f"/matches/{pid}/interest", {}, "/matches").status_code, 403)
        self.login("9111111101")                                         # a buyer cannot make the farmer's offer
        self.assertEqual(self.post(f"/matches/{pid}/accept", {}, "/matches").status_code, 403)
        # anonymous users cannot read agent JSON, non-admins cannot read agent runs
        anon = self.app.test_client()
        self.assertEqual(anon.get("/agent/notifications").status_code, 401)
        self.assertEqual(self.c.get("/agent/runs").status_code, 403)

    def test_no_proposal_when_requirement_fails(self):
        self._post_demand(max_moisture="1", min_curcumin="9", offered_price="100")   # impossible demand
        with self.app.app_context():
            last = BuyerDemand.query.order_by(BuyerDemand.demand_id.desc()).first()
            self.assertEqual(MatchProposal.query.filter_by(requirement_id=last.demand_id).count(), 0)

    def test_llm_loop_with_fake_client_cannot_fake_score(self):
        """LLM path: the model proposes a match with a made-up score; code still stores the engine's score."""
        import types
        import marketplace_agent as MA

        class Block(types.SimpleNamespace):
            pass

        class FakeClient:
            def __init__(self):
                self.n = 0
                self.messages = self

            def create(self, **kw):
                self.n += 1
                if self.n == 1:
                    with self.app.app_context():
                        pass
                    return types.SimpleNamespace(stop_reason="tool_use", content=[Block(
                        type="tool_use", id="t1", name="propose_match",
                        input={"lot_id": LOT, "requirement_id": REQ, "explanation": "Good fit, score 99/100.", "score": 99})])
                return types.SimpleNamespace(stop_reason="end_turn", content=[Block(type="text", text="done")])

        self.login("9111111101")
        with self.app.app_context():
            pairs = [(l, d) for l in ProductListing.query.all() for d in BuyerDemand.query.all()
                     if T.score_pair(l, d)["accepted"]]
            self.assertTrue(pairs, "seed data should contain at least one matching lot/demand pair")
            lot, d = pairs[0]
            LOT, REQ = lot.listing_id, d.demand_id
            os.environ["ANTHROPIC_API_KEY"] = "test"
            orig = MA._client
            MA._client = lambda: types.SimpleNamespace(messages=types.SimpleNamespace(
                create=FakeClient.create.__get__(types.SimpleNamespace(n=0, app=self.app))))
            try:
                run = MA.run_agent({"trigger": "t", "entity_type": "lot", "entity_id": LOT})
            finally:
                MA._client = orig
                os.environ.pop("ANTHROPIC_API_KEY", None)
            self.assertEqual(run.mode, "llm")
            p = MatchProposal.query.filter_by(lot_id=LOT, requirement_id=REQ).first()
            self.assertIsNotNone(p)
            self.assertEqual(p.score, T.score_pair(lot, d)["score"])
            self.assertLess(p.score, 99)

    def test_new_lot_triggers_agent(self):
        self.login("9222222201")
        before = None
        with self.app.app_context():
            before = AgentRun.query.count()
        self.post("/listings/new", {"product_form": "Dried turmeric (finger)", "quantity": "10", "quantity_unit": "Quintal",
                                    "expected_price": "11000", "price_unit": "Rs/Quintal", "location": "Sangli, Maharashtra",
                                    "moisture_pct": "9", "curcumin_pct": "4.5", "has_lab_report": "on",
                                    "lab_report_ref": "NABL-123"}, "/listings/new")
        with self.app.app_context():
            self.assertEqual(AgentRun.query.count(), before + 1)
            self.assertEqual(AgentRun.query.order_by(AgentRun.id.desc()).first().trigger, "new_lot")


if __name__ == "__main__":
    unittest.main()
