"""
Test every Apply link. Run on YOUR computer (needs internet):   python check_links.py
Prints OK / PROBLEM for each scheme. Government sites can be slow or block scripts, so a PROBLEM means
"open it in your browser and look", and OK only means the page loaded. Always click once yourself.
"""
import requests

from scheme_content import APPLY_URLS


HEAD = {"User-Agent": "Mozilla/5.0 (HaldiSetu link check)"}
for name, url in APPLY_URLS.items():
    try:
        r = requests.get(url, headers=HEAD, timeout=25, allow_redirects=True)
        moved = r.url.rstrip("/") != url.rstrip("/")
        status = "OK     " if r.status_code == 200 and not moved else "PROBLEM"
        note = f"HTTP {r.status_code}" + (f", redirected to {r.url}" if moved else "")
    except Exception as exc:  # noqa: BLE001
        status, note = "PROBLEM", f"{type(exc).__name__}: {exc}"
    print(f"{status}  {name[:40]:<40} {url}\n         {note}")