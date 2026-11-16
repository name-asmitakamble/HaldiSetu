"""Event triggers + nightly sweep. Agent runs in a background thread, never in the HTTP request.

Usage:
    from agent_triggers import on_new_lot, on_new_requirement, init_scheduler
    on_new_lot(lot.listing_id)            # call after db.session.commit() when a lot is saved
    on_new_requirement(d.demand_id)       # same for demands
    init_scheduler(app)           # once, in app.py
"""
import threading
from datetime import datetime, timedelta

from flask import current_app

import agent_tools as T
from marketplace_agent import run_agent

 
def ai_mode():
    """'llm' when an Anthropic key is configured, else 'rules' (same matches, templated explanations)."""
    import os
    return "llm" if os.getenv("ANTHROPIC_API_KEY", "").strip() else "rules"


def _spawn(app, event):
    """Run the agent in a background thread (never inside the HTTP request).
    Config: AGENT_AUTORUN=False switches it off; AGENT_SYNC=True runs inline (used by tests)."""
    if not app.config.get("AGENT_AUTORUN", True):
        return
    if app.config.get("TESTING") and not app.config.get("AGENT_SYNC"):
        return                      # keep ordinary tests free of background threads

    def work():
        with app.app_context():
            try:
                run_agent(event)
            except Exception as e:  # noqa: BLE001 - an agent failure must never break the marketplace
                app.logger.error("agent run failed: %s", e)

    if app.config.get("AGENT_SYNC"):
        work()
    else:
        threading.Thread(target=work, daemon=True).start()


def on_new_lot(lot_id):
    _spawn(current_app._get_current_object(),
           {"trigger": "new_lot", "entity_type": "lot", "entity_id": lot_id})


def on_new_requirement(req_id):
    _spawn(current_app._get_current_object(),
           {"trigger": "new_requirement", "entity_type": "requirement", "entity_id": req_id})


def nightly_sweep(app):
    """Re-run the agent for open lots and open demands that have no proposal yet."""
    from models_agent import MatchProposal
    with app.app_context():
        proposed_lots = {p.lot_id for p in MatchProposal.query.all()}
        proposed_reqs = {p.requirement_id for p in MatchProposal.query.all()}
        for lot in T.Lot.query.filter(T.Lot.listing_status.in_(T.LOT_OPEN_STATUSES)).all():
            if lot.listing_id not in proposed_lots:
                run_agent({"trigger": "nightly", "entity_type": "lot", "entity_id": lot.listing_id})
        for req in T.Requirement.query.filter(T.Requirement.status.in_(T.REQ_OPEN_STATUSES)).all():
            if req.demand_id not in proposed_reqs:
                run_agent({"trigger": "nightly", "entity_type": "requirement", "entity_id": req.demand_id})


def init_scheduler(app, hour=2, minute=0):
    """pip install apscheduler. Avoid double start under the Flask reloader."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:          # optional: without it only the instant triggers run
        app.logger.warning("apscheduler not installed: nightly agent sweep disabled")
        return None
    sched = BackgroundScheduler(daemon=True)
    sched.add_job(nightly_sweep, "cron", args=[app], hour=hour, minute=minute,
                  id="marketplace_nightly", replace_existing=True)
    sched.start()
    return sched
 