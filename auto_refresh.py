"""
Keeps the mandi prices current WITHOUT anyone pressing "Sync now".

  * start_background(app) : a small background thread that re-syncs from data.gov.in every AUTO_SYNC_HOURS (default 6)
  * kick(app)             : called when the Market page opens; if the data is older than AUTO_SYNC_HOURS it starts a
                            sync in the background (the page itself never waits for the network)
  * After a successful REAL sync, the SAMPLE demo rows are deleted, so real and sample prices never mix.

Rules: only the official data.gov.in / Agmarknet API is used. If it fails, the old rows stay (shown as Historical,
the page already shows their age) and the next try is after RETRY_MINUTES. Every attempt is written to the audit log.
"""
import os
import threading
import time
from datetime import datetime, timedelta

import requests

from mandi_sync import sync
from market_agent import run_pipeline
from models import MarketPrice, db
from models_market import AuditLog, PriceFlag

RETRY_MINUTES = 30
_lock = threading.Lock()


def _hours(app):
    try:
        return max(1.0, float(app.config.get("AUTO_SYNC_HOURS") or os.getenv("AUTO_SYNC_HOURS", "6")))
    except ValueError:
        return 6.0


def is_due(app):
    """True when the last sync attempt is old enough to try again. Needs an app context."""
    last = AuditLog.query.filter_by(action="mandi_sync").order_by(AuditLog.created_at.desc()).first()
    if last is None:
        return True
    age = datetime.utcnow() - last.created_at
    ok = (last.detail or "").startswith("OK")
    return age > (timedelta(hours=_hours(app)) if ok else timedelta(minutes=RETRY_MINUTES))


def purge_sample():
    """Delete the SAMPLE demo rows once real rows exist. Returns how many were removed."""
    real = MarketPrice.query.filter(~MarketPrice.source_name.like("SAMPLE%")).count()
    if not real:
        return 0
    ids = [r.price_id for r in MarketPrice.query.filter(MarketPrice.source_name.like("SAMPLE%")).all()]
    if ids:
        PriceFlag.query.filter(PriceFlag.price_id.in_(ids)).delete(synchronize_session=False)
        MarketPrice.query.filter(MarketPrice.price_id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
    return len(ids)


def refresh(app, force=False, http=requests):
    """One sync -> flag odd records -> price alerts -> drop sample rows. Safe to call from any thread."""
    if not os.getenv("DATA_GOV_API_KEY", "").strip() or not _lock.acquire(blocking=False):
        return None
    try:
        with app.app_context():
            if not force and not is_due(app):
                return None
            res = run_pipeline(sync_fn=lambda: sync(http=http))
            if res["sync"] and res["sync"][0]:
                res["sample_removed"] = purge_sample()
            return res
    except Exception:  # noqa: BLE001 — a background job must never take the website down
        return None
    finally:
        _lock.release()


def kick(app):
    """Start a background refresh if the data is stale. Cheap when it is not."""
    if app.config.get("TESTING") or not os.getenv("DATA_GOV_API_KEY", "").strip():
        return
    threading.Thread(target=refresh, args=(app,), daemon=True).start()


def start_background(app):
    """Timer thread. Skipped in tests, without an API key, and in the debug-reloader parent process."""
    if app.config.get("TESTING") or not os.getenv("DATA_GOV_API_KEY", "").strip():
        return
    if os.getenv("FLASK_DEBUG", "0") == "1" and os.getenv("WERKZEUG_RUN_MAIN") != "true":
        return

    def loop():
        time.sleep(20)                      # let the server start first
        while True:
            refresh(app)
            time.sleep(15 * 60)             # re-check every 15 min; refresh() itself decides whether a sync is due

    threading.Thread(target=loop, daemon=True, name="mandi-auto-sync").start()