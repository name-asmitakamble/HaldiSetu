"""
Import turmeric mandi prices from a CSV or data.gov.in / AGMARKNET API.

Header names are matched loosely (case-insensitive, spaces -> underscores). Accepted names:
    state | district | market / market_name / mandi | commodity | variety | grade
    arrival_date / reporting_date / date | min_price | max_price | modal_price | unit
Rows whose commodity is not turmeric are skipped (if a commodity column exists).

Record Synchronization:
- Existing genuine records are UPDATED with latest modal, min, and max prices, preserving history.
- New records are inserted.
- Suitable unique key matches on (market_name, variety, reporting_date), validated against (state, district).
- Returns detailed stats: added, updated, skipped_duplicate, skipped_invalid, skipped_other_commodity.
"""
import csv
import io
import sys
from datetime import datetime

from models import db, MarketPrice

DATE_FORMATS = (
    "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%m/%d/%Y",
    "%Y/%m/%d", "%d.%m.%Y"
)
ALIASES = {
    "market": "market_name", "market_name": "market_name", "mandi": "market_name",
    "arrival_date": "reporting_date", "reporting_date": "reporting_date", "date": "reporting_date",
    "min_price": "minimum_price", "minimum_price": "minimum_price", "min_x0020_price": "minimum_price",
    "max_price": "maximum_price", "maximum_price": "maximum_price", "max_x0020_price": "maximum_price",
    "modal_price": "modal_price", "modal_x0020_price": "modal_price",
    "state": "state", "district": "district", "commodity": "commodity",
    "variety": "variety", "unit": "unit",
}


def _date(s):
    if not s:
        return None
    s = str(s).strip()
    # Strip any trailing time or timezone components if present
    if "T" in s:
        s = s.split("T")[0].strip()
    elif " " in s:
        s = s.split(" ")[0].strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _num(s):
    if s is None:
        return None
    try:
        clean = str(s).replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "").strip()
        v = float(clean)
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def import_csv_text(text, source_name):
    """Returns dict(added, updated, skipped_duplicate, skipped_invalid, skipped_other_commodity)."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return {"added": 0, "updated": 0, "skipped_duplicate": 0, "skipped_invalid": 0, "skipped_other_commodity": 0}
    return import_rows(reader, source_name)


def import_rows(rows, source_name):
    """
    Core importer used by CSV upload and the data.gov.in API sync (rows = iterable of dicts).
    Updates existing records if matching (market, variety, date) is found; otherwise inserts.
    """
    stats = {
        "added": 0,
        "updated": 0,
        "skipped_duplicate": 0,
        "skipped_invalid": 0,
        "skipped_other_commodity": 0,
    }

    for row in rows:
        r = {}
        for h, v in row.items():
            key = ALIASES.get((str(h) or "").strip().lower().replace(" ", "_"))
            if key:
                r[key] = (str(v) if v is not None else "").strip()

        # Commodity validation
        commodity_str = (r.get("commodity") or "").lower()
        if commodity_str and not any(k in commodity_str for k in ("turmeric", "haldi", "curcuma")):
            stats["skipped_other_commodity"] += 1
            continue

        d = _date(r.get("reporting_date"))
        modal = _num(r.get("modal_price"))
        lo = _num(r.get("minimum_price"))
        hi = _num(r.get("maximum_price"))
        market_name = (r.get("market_name") or "").strip()
        state = (r.get("state") or "").strip() or None
        district = (r.get("district") or "").strip() or None
        variety = (r.get("variety") or "").strip() or None
        unit = (r.get("unit") or "").strip() or "Rs/Quintal"

        if not d or not market_name or modal is None:
            stats["skipped_invalid"] += 1
            continue

        if lo and hi and lo > hi:
            lo, hi = hi, lo

        # Check for existing record to update
        q_exists = MarketPrice.query.filter_by(
            market_name=market_name,
            variety=variety,
            reporting_date=d
        )
        if state:
            q_with_state = q_exists.filter_by(state=state)
            if q_with_state.first():
                q_exists = q_with_state
        if district:
            q_with_dist = q_exists.filter_by(district=district)
            if q_with_dist.first():
                q_exists = q_with_dist

        exists = q_exists.first()

        if exists:
            # Check if prices or details changed
            has_changes = (
                exists.modal_price != modal or
                exists.minimum_price != lo or
                exists.maximum_price != hi or
                (state and exists.state != state) or
                (district and exists.district != district)
            )
            if has_changes:
                exists.modal_price = modal
                exists.minimum_price = lo
                exists.maximum_price = hi
                if state:
                    exists.state = state
                if district:
                    exists.district = district
                if unit:
                    exists.unit = unit
                exists.source_name = source_name
                exists.imported_at = datetime.utcnow()
                stats["updated"] += 1
            else:
                stats["skipped_duplicate"] += 1
            continue

        # Insert new record
        db.session.add(MarketPrice(
            commodity="Turmeric",
            state=state,
            district=district,
            market_name=market_name,
            variety=variety,
            reporting_date=d,
            minimum_price=lo,
            maximum_price=hi,
            modal_price=modal,
            unit=unit,
            source_name=source_name,
            imported_at=datetime.utcnow()
        ))
        stats["added"] += 1

    db.session.commit()
    return stats


if __name__ == "__main__":
    from app import create_app

    if len(sys.argv) < 3:
        sys.exit('Usage: python price_import.py <file.csv> "<source description>"')
    with create_app().app_context():
        with open(sys.argv[1], encoding="utf-8-sig") as fh:
            print(import_csv_text(fh.read(), sys.argv[2]))
