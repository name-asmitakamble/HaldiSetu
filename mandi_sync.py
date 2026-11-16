"""
Daily mandi-price sync from the official Open Government Data API (data.gov.in / Agmarknet).

  Dataset : "Current Daily Price of Various Commodities from Various Markets (Mandi)"
            https://data.gov.in/catalog/current-daily-price-various-commodities-various-markets-mandi
  Resource: 9ef84268-d588-465a-a308-a864a43d0070
  API docs: https://data.gov.in/help/how-use-datasets-apis

  Official AGMARKNET fields:
    state, district, market, commodity, variety,
    arrival_date  (format: DD/MM/YYYY)
    min_price, max_price, modal_price   (Rs/Quintal)

Pagination Implementation:
- Uses data.gov.in standard offset-based pagination: limit=500 per page, offset=0, 500, 1000...
- Checks response "total" count and continues requesting pages until all matching records are fetched.
- Deduplicates across pages using unique key: (state, district, market, variety, arrival_date).
- Never restricts to any single state or district — queries all nationwide turmeric records.
- In case of network interruption on later pages, preserves all successfully fetched records
  and marks the sync as PARTIAL rather than crashing or inventing data.
"""
import os
from datetime import datetime

import requests

from price_import import import_rows

RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"
API_URL = f"https://api.data.gov.in/resource/{RESOURCE_ID}"

EXPECTED_FIELDS = {"state", "district", "market", "commodity", "variety",
                   "arrival_date", "min_price", "max_price", "modal_price"}


def _validate_response(records):
    """
    Validate that retrieved records contain expected fields.
    Returns (ok: bool, message: str).
    """
    if not records:
        return True, "ok (no records to validate)"
    sample = set(records[0].keys())
    missing = EXPECTED_FIELDS - sample
    if missing:
        return False, (
            f"API response missing expected fields: {sorted(missing)}. "
            f"Got fields: {sorted(sample)}."
        )
    return True, "ok"


def fetch_records(api_key, commodity="Turmeric", page_size=500, max_pages=100, http=requests):
    """
    Fetch all available turmeric records from the data.gov.in AGMARKNET API across all
    states and districts using pagination (offset / limit).

    Returns:
      (records: list[dict], is_partial: bool, total_api: int|None, error_msg: str|None)
    """
    records = []
    seen = set()
    offset = 0
    total_api = None
    is_partial = False
    error_msg = None

    for page in range(max_pages):
        try:
            r = http.get(
                API_URL,
                params={
                    "api-key": api_key,
                    "format": "json",
                    "offset": offset,
                    "limit": page_size,
                    "filters[commodity]": commodity,
                },
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            if page > 0:
                # We already fetched some pages; preserve them as a partial sync
                is_partial = True
                error_msg = f"Pagination interrupted at page {page + 1} (offset {offset}): {type(exc).__name__}: {exc}"
                break
            else:
                # First page failed; re-raise to caller
                raise

        batch = data.get("records", [])

        # Read API total if available
        if "total" in data:
            try:
                total_api = int(data["total"])
            except (ValueError, TypeError):
                pass

        for rec in batch:
            key = (
                str(rec.get("state", "")).strip().lower(),
                str(rec.get("district", "")).strip().lower(),
                str(rec.get("market", "")).strip().lower(),
                str(rec.get("variety", "")).strip().lower(),
                str(rec.get("arrival_date", "")).strip(),
            )
            if key not in seen:
                seen.add(key)
                records.append(rec)

        # Stop conditions:
        # 1. Received less than a full page
        if len(batch) < page_size:
            break

        # 2. Reached or exceeded total reported by API
        if total_api is not None and (offset + len(batch)) >= total_api:
            break

        offset += len(batch)

    return records, is_partial, total_api, error_msg


def sync(api_key=None, http=requests):
    """
    Pull latest nationwide turmeric mandi prices from data.gov.in.
    Returns:
      (ok: bool, message: str, stats: dict|None)
    Caller must be inside an application context.
    """
    api_key = api_key or os.getenv("DATA_GOV_API_KEY", "").strip()
    if not api_key:
        return (
            False,
            "DATA_GOV_API_KEY is not set in .env. Register at data.gov.in "
            "(My Account -> API key) to enable live daily mandi synchronization.",
            None,
        )

    try:
        records, is_partial, total_api, error_msg = fetch_records(api_key, http=http)
    except Exception as exc:  # noqa: BLE001
        return False, f"Could not reach data.gov.in: {type(exc).__name__}: {exc}", None

    if not records:
        return (
            False,
            "The API returned 0 turmeric records across all districts. "
            "Verify your API key at data.gov.in and check whether the dataset is currently updated.",
            None,
        )

    # Validate schema
    valid, val_msg = _validate_response(records)
    if not valid:
        return False, f"API schema validation failed: {val_msg}", None

    now_str = datetime.now().strftime("%d %b %Y %H:%M")
    src = f"Agmarknet via data.gov.in API (synced {now_str})"
    stats = import_rows(records, src)

    # Count distinct districts and states in the imported batch
    batch_states = len({r.get("state") for r in records if r.get("state")})
    batch_districts = len({r.get("district") for r in records if r.get("district")})
    batch_markets = len({r.get("market") for r in records if r.get("market")})

    if is_partial:
        msg = (
            f"PARTIAL sync: Retrieved {len(records)} records across {batch_states} states, "
            f"{batch_districts} districts, {batch_markets} markets (API reported total: {total_api or 'unknown'}). "
            f"Added: {stats.get('added', 0)}, Updated: {stats.get('updated', 0)}. "
            f"Notice: {error_msg}"
        )
        return True, msg, stats
    else:
        msg = (
            f"OK (FULL): Retrieved all {len(records)} records across {batch_states} states, "
            f"{batch_districts} districts, {batch_markets} markets. "
            f"Added: {stats.get('added', 0)}, Updated: {stats.get('updated', 0)}."
        )
        return True, msg, stats


if __name__ == "__main__":
    from app import create_app

    with create_app().app_context():
        ok, msg, _ = sync()
        print(("OK: " if ok else "FAILED: ") + msg)
