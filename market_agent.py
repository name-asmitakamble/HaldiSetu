"""
Market intelligence agent + small orchestrator.

  flag_anomalies()  mark odd mandi records (modal outside min-max, or a >40% jump vs the previous record of the same
                    market+variety). Records are KEPT and shown with a warning; nothing is deleted or "corrected".
  summary(lang)     plain-language daily summary (English / Marathi / Hindi) built from the stored numbers only.
  check_alerts()    farmers' price alerts -> in-app notifications (one per alert per data date). No SMS/e-mail.
  run_pipeline()    the orchestrator: sync (optional) -> flag -> alerts, every step written to the audit log.

CLI (daily, e.g. Windows Task Scheduler / cron):   python market_agent.py
"""
from datetime import date

from sqlalchemy import func

from access import audit
from models import MarketPrice, db
from models_market import Notification, PriceAlert, PriceFlag

JUMP = 0.40     # flag a day-to-day change larger than 40% for human review (a review threshold, not a market fact)


def _rows():
    return MarketPrice.query.filter(func.lower(MarketPrice.commodity).like("%turmeric%"),
                                    MarketPrice.reporting_date.isnot(None)).all()


def flag_anomalies(window_days=60):
    rows = _rows()
    if not rows:
        return 0
    latest = max(r.reporting_date for r in rows)
    rows = sorted((r for r in rows if (latest - r.reporting_date).days <= window_days),
                  key=lambda r: (r.market_name or "", r.variety or "", r.reporting_date))
    seen = {(f.price_id, f.code) for f in PriceFlag.query.all()}
    prev, added = {}, 0
    for r in rows:
        found = []
        if r.minimum_price and r.maximum_price and r.modal_price and not (r.minimum_price <= r.modal_price <= r.maximum_price):
            found.append(("range", "Modal price is outside the reported minimum–maximum range"))
        p = prev.get((r.market_name, r.variety))
        if p and p.modal_price and r.modal_price and p.reporting_date < r.reporting_date:
            ch = (r.modal_price - p.modal_price) / p.modal_price
            if abs(ch) > JUMP:
                found.append(("jump", f"Modal price changed {ch:+.0%} since {p.reporting_date:%d %b %Y}"))
        prev[(r.market_name, r.variety)] = r
        for code, reason in found:
            if (r.price_id, code) not in seen:
                db.session.add(PriceFlag(price_id=r.price_id, code=code, reason=reason))
                seen.add((r.price_id, code))
                added += 1
    db.session.commit()
    return added


T = {"en": ("On {d}, {n} markets reported turmeric. Average modal price ₹{avg}/quintal; highest {hm} (₹{hi}), lowest {lm} (₹{lo}).",
            " The average is ₹{x} {w} than on {pd}.", "higher", "lower", " Source: {src}.", " SAMPLE DATA — not real prices.", " Records are {a} days old (historical)."),
     "mr": ("{d} रोजी {n} बाजारांनी हळदीचे भाव नोंदवले. सरासरी मोडल भाव ₹{avg}/क्विंटल; सर्वाधिक {hm} (₹{hi}), सर्वात कमी {lm} (₹{lo}).",
            " सरासरी {pd} पेक्षा ₹{x} {w} आहे.", "जास्त", "कमी", " स्रोत: {src}.", " नमुना माहिती — खरे भाव नाहीत.", " ही नोंद {a} दिवस जुनी आहे (जुनी माहिती)."),
     "hi": ("{d} को {n} मंडियों ने हल्दी के भाव दर्ज किए। औसत मॉडल भाव ₹{avg}/क्विंटल; सबसे ऊँचा {hm} (₹{hi}), सबसे कम {lm} (₹{lo})।",
            " औसत {pd} की तुलना में ₹{x} {w} है।", "अधिक", "कम", " स्रोत: {src}।", " नमूना डेटा — असली भाव नहीं।", " यह रिकॉर्ड {a} दिन पुराना है (पुराना डेटा)।")}


def summary(lang="en"):
    """Returns dict(text, date) or None. Numbers only come from stored mandi records."""
    rows = [r for r in _rows() if r.modal_price]
    if not rows:
        return None
    lang = lang if lang in T else "en"
    latest = max(r.reporting_date for r in rows)
    today = [r for r in rows if r.reporting_date == latest]
    by_m = {}
    for r in today:
        by_m.setdefault(r.market_name, []).append(r.modal_price)
    mm = {m: sum(v) / len(v) for m, v in by_m.items()}
    hm, lm = max(mm, key=mm.get), min(mm, key=mm.get)
    avg = sum(mm.values()) / len(mm)
    base, ptxt, w_hi, w_lo, srcf, samp, old = T[lang]
    text = base.format(d=f"{latest:%d %b %Y}", n=len(mm), avg=f"{avg:,.0f}", hm=hm, hi=f"{mm[hm]:,.0f}", lm=lm, lo=f"{mm[lm]:,.0f}")
    earlier = sorted({r.reporting_date for r in rows if r.reporting_date < latest})
    if earlier:
        pd = earlier[-1]
        pv = [r.modal_price for r in rows if r.reporting_date == pd]
        diff = avg - sum(pv) / len(pv)
        text += ptxt.format(x=f"{abs(diff):,.0f}", w=w_hi if diff >= 0 else w_lo, pd=f"{pd:%d %b}")
    srcs = sorted({r.source_name or "unknown" for r in today})
    text += srcf.format(src="; ".join(srcs)[:120])
    if any((r.source_name or "").upper().startswith("SAMPLE") for r in today):
        text += samp
    age = (date.today() - latest).days
    if age > 7:
        text += old.format(a=age)
    return {"text": text, "date": latest}


def check_alerts():
    rows = [r for r in _rows() if r.modal_price]
    if not rows:
        return 0
    latest = max(r.reporting_date for r in rows)
    by_m = {}
    for r in rows:
        if r.reporting_date == latest:
            by_m.setdefault(r.market_name, []).append(r.modal_price)
    mm = {m: sum(v) / len(v) for m, v in by_m.items()}
    fired = 0
    for a in PriceAlert.query.filter_by(active=True).all():
        if a.last_triggered_on == latest:
            continue
        if a.market_name:
            if a.market_name not in mm:
                continue
            label, val = a.market_name, mm[a.market_name]
        else:
            label = max(mm, key=mm.get)
            val = mm[label]
        hit = val > a.threshold_q if a.direction == "above" else val < a.threshold_q
        if hit:
            db.session.add(Notification(user_id=a.user_id, text=(
                f"Price alert: {label} modal price ₹{val:,.0f}/q is {a.direction} your ₹{a.threshold_q:,.0f}/q "
                f"(data of {latest:%d %b %Y})."[:300])))
            a.last_triggered_on = latest
            fired += 1
    db.session.commit()
    return fired


def run_pipeline(sync_fn=None):
    """Orchestrator: [sync] -> flag anomalies -> refresh industry stats -> price alerts. Each step is audited. Returns a result dict."""
    result = {"sync": None, "flagged": 0, "industry_stats": None, "alerts": 0}
    if sync_fn:
        ok, msg, _ = sync_fn()
        result["sync"] = (ok, msg)
        audit("mandi_sync", "market_prices", None, ("OK: " if ok else "FAILED: ") + msg)
        db.session.commit()
    result["flagged"] = flag_anomalies()
    audit("agent_market_flags", "market_prices", None, f"{result['flagged']} new flag(s)")

    # Step 3: Refresh industry stats & requirements
    try:
        from industry_agent import refresh_industry_stats
        result["industry_stats"] = refresh_industry_stats()
        audit("agent_industry_stats", "buyer_demands", None, f"{len(result['industry_stats'])} sector(s) refreshed")
    except Exception as e:
        result["industry_stats"] = str(e)

    result["alerts"] = check_alerts()
    audit("agent_price_alerts", "price_alerts", None, f"{result['alerts']} notification(s)")
    db.session.commit()
    return result


if __name__ == "__main__":
    from app import create_app
    from mandi_sync import sync

    with create_app().app_context():
        print(run_pipeline(sync_fn=sync))
