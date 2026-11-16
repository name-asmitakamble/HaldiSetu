"""
Lot intake agent: farmer types or speaks (Marathi / Hindi / English) -> lot form fields + questions for what is missing.

  Mode "rules": regex/keyword parser (works offline; handles Devanagari digits and common Marathi words)
  Mode "llm"  : Claude extracts the fields (llm.py), the result is validated by the SAME sanitiser, and any field
                it left empty is filled from the rules. Nothing is saved here: the farmer sees the filled form,
                corrects it and presses Publish (human confirms).
"""
import re

import llm

FORMS = ["Fresh rhizome", "Dried turmeric (finger)", "Dried turmeric (bulb)", "Polished turmeric", "Turmeric powder"]
DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
UNIT_WORDS = {"Quintal": ["quintals", "quintal", "qtl", "क्विंटल", "क्विन्टल", "क्विंटल्स"],
              "Tonne": ["tonnes", "tonne", "tons", "ton", "टन"],
              "Kg": ["kilogram", "kgs", "kg", "kilo", "किलोग्रॅम", "किलो", "कि.ग्रॅ"]}
FORM_WORDS = [("Turmeric powder", ["powder", "पावडर", "पूड", "पुड"]),
              ("Fresh rhizome", ["fresh", "rhizome", "ओली", "ओला", "ताजी", "ताजा", "कच्ची", "कच्चा"]),
              ("Polished turmeric", ["polished", "पॉलिश"]),
              ("Dried turmeric (bulb)", ["bulb", "गड्डा", "गड्डे"]),
              ("Dried turmeric (finger)", ["dried", "dry", "finger", "वाळलेली", "वाळवलेली", "वाळलेले", "सुकी", "सुकलेली", "हळकुंड", "सुके"])]
PLACES_DEV = {"सांगली": "Sangli", "कोल्हापूर": "Kolhapur", "सातारा": "Satara", "हिंगोली": "Hingoli", "नांदेड": "Nanded",
              "वसमत": "Vasmat", "परभणी": "Parbhani", "पुणे": "Pune", "सोलापूर": "Solapur", "नाशिक": "Nashik",
              "निझामाबाद": "Nizamabad", "इरोड": "Erode", "सेलम": "Salem", "मुंबई": "Mumbai"}
NUM = r"(\d[\d,]*(?:\.\d+)?)"

REQUIRED = ["quantity", "product_form", "location", "expected_price"]
ADVISED = ["moisture_pct", "curcumin_pct"]
QUESTIONS = {
    "quantity": {"en": "How much turmeric do you have (for example 5 quintal)?", "mr": "तुमच्याकडे किती हळद आहे (उदा. ५ क्विंटल)?"},
    "product_form": {"en": "Is it fresh, dried (finger), bulb, polished or powder?", "mr": "हळद ओली आहे, वाळलेली (हळकुंड), गड्डा, पॉलिश की पावडर?"},
    "location": {"en": "Where is the lot (village / district)?", "mr": "माल कुठे आहे (गाव / जिल्हा)?"},
    "expected_price": {"en": "What price per quintal do you expect?", "mr": "प्रति क्विंटल किती भाव अपेक्षित आहे?"},
    "moisture_pct": {"en": "What is the moisture percentage (optional, helps matching)?", "mr": "ओलावा किती टक्के आहे (ऐच्छिक, मॅचिंगसाठी उपयुक्त)?"},
    "curcumin_pct": {"en": "Is curcumin tested? If yes, what percentage (optional)?", "mr": "कर्क्युमिनची चाचणी झाली आहे का? असल्यास किती टक्के (ऐच्छिक)?"},
}


def _num(s):
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def _blank(text, m):
    return text[:m.start()] + " " * (m.end() - m.start()) + text[m.end():]


def parse_rules(text, known_places=()):
    raw = (text or "").translate(DIGITS)
    t = raw.lower()
    f = {}

    m = re.search(r"(?:curcumin|कर्क्युमिन|करक्युमिन|कर्क्यूमिन)\D{0,15}?" + NUM, t)
    if m:
        f["curcumin_pct"] = _num(m.group(1))
        t = _blank(t, m)
    m = re.search(r"(?:moisture|ओलावा|आर्द्रता)\D{0,15}?" + NUM, t)
    if m:
        f["moisture_pct"] = _num(m.group(1))
        t = _blank(t, m)

    price = None
    for pat in (r"(?:₹|rs\.?|inr|रु\.?|रुपये)\s*" + NUM, r"(?:price|rate|भाव|दर)\D{0,12}?" + NUM,
                r"(?:at|@)\s*" + NUM + r"\s*(?:per|/|प्रति)", NUM + r"\s*(?:rs\b|रुपये|रु\b|₹)"):
        m = re.search(pat, t)
        if m:
            price = _num(m.group(1))
            t = _blank(t, m)
            break
    if price:
        f["expected_price"] = price
        f["price_unit"] = "Rs/Kg" if re.search(r"(?:per|/|प्रति)\s*(?:kg|kilo|किलो)", raw.lower()) else "Rs/Quintal"

    for unit, words in UNIT_WORDS.items():
        m = re.search(NUM + r"\s*(?:" + "|".join(re.escape(w) for w in words) + ")", t)
        if m:
            f["quantity"], f["quantity_unit"] = _num(m.group(1)), unit
            break

    for form, words in FORM_WORDS:
        if any(w in t for w in words):
            f["product_form"] = form
            break

    place = None
    for dev, eng in PLACES_DEV.items():
        if dev in raw:
            place = eng
            break
    if not place:
        for p in sorted({p for p in known_places if p}, key=len, reverse=True):
            if p.lower() in t:
                place = p
                break
    if not place:
        m = re.search(r"\b(?:in|at|from|near)\s+([a-z][a-z ]{2,30}?)(?=[,.]|\s+(?:by|for|with|at|from|price|rate)\b|$)", t)
        if m:
            place = m.group(1).strip().title()
    if place:
        f["location"] = place
    return f


def sanitize(d):
    """Validate a field dict (from rules OR the LLM) so nothing unexpected reaches the form."""
    out = {}

    def num(key, lo, hi):
        v = d.get(key)
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        return v if lo < v <= hi else None

    q = num("quantity", 0, 1_000_000)
    if q is not None:
        out["quantity"] = q
        out["quantity_unit"] = d.get("quantity_unit") if d.get("quantity_unit") in UNIT_WORDS else "Quintal"
    p = num("expected_price", 0, 10_000_000)
    if p is not None:
        out["expected_price"] = p
        out["price_unit"] = d.get("price_unit") if d.get("price_unit") in ("Rs/Quintal", "Rs/Kg") else "Rs/Quintal"
    if d.get("product_form") in FORMS:
        out["product_form"] = d["product_form"]
    loc = str(d.get("location") or "").strip()[:120]
    if len(loc) >= 3:
        out["location"] = loc
    for k in ADVISED:
        v = d.get(k)
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if 0 <= v <= 100:
            out[k] = v
    var = str(d.get("variety") or "").strip()[:60]
    if var:
        out["variety"] = var
    return out


LLM_SYSTEM = (
    "You extract turmeric lot details from a farmer's message written in Marathi, Hindi or English. "
    "Reply with ONLY a JSON object with these keys: quantity (number or null), quantity_unit (Quintal|Kg|Tonne|null), "
    "product_form (one of: " + ", ".join(FORMS) + " or null), location (place name in English letters or null), "
    "expected_price (number or null), price_unit (Rs/Quintal|Rs/Kg|null), moisture_pct (number or null), "
    "curcumin_pct (number or null), variety (string or null). Use null for anything not stated. Never guess or invent.")


def parse_lot_text(text, known_places=()):
    text = (text or "").strip()[:500]
    fields, mode = {}, "rules"
    ai = llm.complete_json(LLM_SYSTEM, text) if text else None
    if ai:
        fields, mode = sanitize(ai), "llm"
    for k, v in sanitize(parse_rules(text, known_places)).items():
        fields.setdefault(k, v)          # rules fill whatever the LLM left empty
    missing = [k for k in REQUIRED + ADVISED if k not in fields]
    return {"mode": mode, "fields": fields, "missing": missing,
            "required_missing": [k for k in missing if k in REQUIRED],
            "questions": {lang: [QUESTIONS[k][lang] for k in missing] for lang in ("en", "mr")}}
