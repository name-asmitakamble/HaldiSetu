"""
Rule-based government-scheme matching (Module 3). No LLM — plain, explainable rules.

Each Scheme.eligibility_rules is a JSON object. Supported keys (all optional):
    "states"        : ["Maharashtra", ...]   scheme limited to these states (absent = all India)
    "owns_land"     : true                   farmer must own agricultural land
    "min_land_ha"   : 0.5                    minimum landholding in hectares
    "max_land_ha"   : 2.0                    maximum landholding in hectares
    "farmer_types"  : ["owner","tenant"]     allowed farmer categories
    "note"          : "free text"            shown to the user as "verify this"

Each check returns True (pass) / False (fail) / None (cannot decide: input missing).
Scheme status:  any False -> "no" | else any None -> "unknown" | else "match".
"""
import json


def _n(v):
    return (v or "").strip().lower()


def parse_profile(args):
    """Build a clean profile dict from request.args. Collects only what matching needs."""
    land = None
    raw = (args.get("land_ha") or "").strip()
    if raw:
        try:
            land = float(raw)
            if land < 0 or land > 10000:
                land = None
        except ValueError:
            land = None
    return {
        "state": (args.get("state") or "").strip(),
        "land_ha": land,
        "owns_land": _n(args.get("owns_land")),       # "yes" / "no" / ""
        "farmer_type": _n(args.get("farmer_type")),   # owner / tenant / sharecropper / ""
    }


def evaluate(rules, profile):
    checks = []

    def add(label, result, detail):
        checks.append({"label": label, "result": result, "detail": detail})

    states = rules.get("states")
    if states:
        p = _n(profile["state"])
        add("State", None if not p else p in [_n(s) for s in states],
            "Applies in: " + ", ".join(states) + ("" if p else " (state not provided)"))

    if rules.get("owns_land") is True:
        v = profile["owns_land"]
        add("Owns agricultural land", None if not v else v == "yes",
            "Scheme requires land ownership" + ("" if v else " (not provided)"))

    land = profile["land_ha"]
    if rules.get("min_land_ha") is not None:
        add("Minimum landholding", None if land is None else land >= rules["min_land_ha"],
            f"At least {rules['min_land_ha']} ha" + ("" if land is not None else " (not provided)"))
    if rules.get("max_land_ha") is not None:
        add("Maximum landholding", None if land is None else land <= rules["max_land_ha"],
            f"Up to {rules['max_land_ha']} ha" + ("" if land is not None else " (not provided)"))

    types = rules.get("farmer_types")
    if types:
        t = profile["farmer_type"]
        add("Farmer category", None if not t else t in [_n(x) for x in types],
            "Open to: " + ", ".join(types) + ("" if t else " (not provided)"))

    results = [c["result"] for c in checks]
    if False in results:
        status = "no"
    elif None in results:
        status = "unknown"
    else:
        status = "match"
    return status, checks


def match_schemes(schemes, profile):
    out = []
    for s in schemes:
        try:
            rules = json.loads(s.eligibility_rules or "{}")
        except json.JSONDecodeError:
            rules = {}
        status, checks = evaluate(rules, profile)
        out.append({"scheme": s, "status": status, "checks": checks, "note": rules.get("note")})
    order = {"match": 0, "unknown": 1, "no": 2}
    out.sort(key=lambda r: (order[r["status"]], r["scheme"].scheme_name))
    return out
