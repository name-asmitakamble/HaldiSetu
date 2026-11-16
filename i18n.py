"""
Languages for the scheme module: English (en), Hindi (hi), Marathi (mr).
NOTE: Hindi/Marathi text was written for this project and should be read by a native speaker
before the final demo — fix any wording directly in this file / scheme_content.py.
"""
LANGS = {"en": "English", "hi": "हिन्दी", "mr": "मराठी"}

STAGE_ORDER = ["pre_sowing", "sowing", "growing", "harvest", "post_harvest", "selling"]
STAGES = {
    "pre_sowing": {"en": "Before planting", "hi": "रोपाई से पहले", "mr": "लागवडीपूर्वी"},
    "sowing": {"en": "Planting / sowing", "hi": "रोपाई / बुवाई", "mr": "लागवड / पेरणी"},
    "growing": {"en": "Crop growing", "hi": "फसल की बढ़वार", "mr": "पीक वाढीचा काळ"},
    "harvest": {"en": "Harvest", "hi": "कटाई / खुदाई", "mr": "काढणी"},
    "post_harvest": {"en": "Post-harvest (boiling, drying, storage)", "hi": "कटाई के बाद (उबालना, सुखाना, भंडारण)",
                     "mr": "काढणीनंतर (शिजवणे, वाळवणे, साठवण)"},
    "selling": {"en": "Selling", "hi": "बिक्री", "mr": "विक्री"},
}
DOCS = {
    "aadhaar": {"en": "Aadhaar card", "hi": "आधार कार्ड", "mr": "आधार कार्ड"},
    "aadhaar_mobile": {"en": "Mobile number linked to Aadhaar", "hi": "आधार से जुड़ा मोबाइल नंबर", "mr": "आधारशी जोडलेला मोबाइल नंबर"},
    "bank": {"en": "Bank passbook / account details", "hi": "बैंक पासबुक / खाता विवरण", "mr": "बँक पासबुक / खाते तपशील"},
    "land_record": {"en": "Land record (7/12 or 8A)", "hi": "भूमि अभिलेख (7/12 या 8A)", "mr": "जमिनीचा उतारा (७/१२ किंवा ८अ)"},
    "tenancy": {"en": "Tenancy / lease agreement", "hi": "किरायेदारी / पट्टा समझौता", "mr": "भाडेकरार / कुळ करार"},
    "sowing": {"en": "Sowing (crop) declaration", "hi": "बुवाई (फसल) घोषणा", "mr": "पेरणी (पीक) घोषणापत्र"},
    "photo": {"en": "Passport-size photo", "hi": "पासपोर्ट साइज फोटो", "mr": "पासपोर्ट आकाराचा फोटो"},
    "project_report": {"en": "Project report (for processing / storage projects)",
                       "hi": "परियोजना रिपोर्ट (प्रसंस्करण / भंडारण हेतु)", "mr": "प्रकल्प अहवाल (प्रक्रिया / साठवणीसाठी)"},
}

T = {
    "en": {
        "title": "Government scheme assistant", "intro": "Tell us about your farm. The agent checks every scheme's eligibility rules and explains the ones that may suit you. No ID numbers are collected.",
        "state": "State", "district": "District", "land": "Land you cultivate (hectares)", "owns": "Do you own the land?",
        "yes": "Yes", "no": "No", "ftype": "Farmer category", "owner": "Owner-cultivator", "tenant": "Tenant farmer",
        "sharecropper": "Sharecropper", "stage": "Current stage of turmeric farming", "docs_have": "Tick the documents you already have",
        "language": "Language", "save": "Save and find schemes", "select": "— select —",
        "results": "Your schemes", "match": "May be eligible", "unknown": "Need more information", "no_match": "Does not match your answers",
        "now": "Fits your current stage", "later": "Becomes relevant at:", "docs_count": "Documents you have: {have} of {need}",
        "missing": "Still needed:", "all_docs": "You have all the listed documents.", "highlights": "Key points", "steps": "How to apply",
        "apply": "Open the official page to apply", "why": "Why", "calendar": "Your action calendar",
        "summary": "{n} scheme(s) may suit you; {now} fit your current stage.",
        "disclaimer": "These are potentially relevant schemes, not approvals. Final eligibility and benefits are decided by the government authority. Always apply only through the official page.",
        "verified": "Last verified", "not_verified": "not yet verified", "login": "Please log in as a farmer to use the scheme assistant.",
        "no_profile": "Fill in the form above to see your schemes.", "none": "none",
    },
    "hi": {
        "title": "सरकारी योजना सहायक", "intro": "अपने खेत के बारे में बताइए। एजेंट हर योजना के पात्रता नियम जाँचकर आपके लिए उपयोगी योजनाएँ समझाएगा। कोई पहचान नंबर नहीं लिया जाता।",
        "state": "राज्य", "district": "ज़िला", "land": "आप कितनी ज़मीन पर खेती करते हैं (हेक्टेयर)", "owns": "क्या ज़मीन आपके नाम है?",
        "yes": "हाँ", "no": "नहीं", "ftype": "किसान की श्रेणी", "owner": "स्वयं खेती करने वाले मालिक", "tenant": "किरायेदार किसान",
        "sharecropper": "बटाईदार", "stage": "हल्दी की खेती की वर्तमान अवस्था", "docs_have": "जो दस्तावेज़ आपके पास हैं उन पर निशान लगाएँ",
        "language": "भाषा", "save": "सहेजें और योजनाएँ खोजें", "select": "— चुनें —",
        "results": "आपकी योजनाएँ", "match": "पात्र हो सकते हैं", "unknown": "और जानकारी चाहिए", "no_match": "आपके उत्तरों से मेल नहीं खाती",
        "now": "आपकी वर्तमान अवस्था के अनुकूल", "later": "इस अवस्था में उपयोगी:", "docs_count": "आपके पास दस्तावेज़: {have}/{need}",
        "missing": "अभी भी चाहिए:", "all_docs": "सूची के सभी दस्तावेज़ आपके पास हैं।", "highlights": "मुख्य बातें", "steps": "आवेदन कैसे करें",
        "apply": "आवेदन के लिए आधिकारिक पेज खोलें", "why": "कारण", "calendar": "आपका कार्य-कैलेंडर",
        "summary": "{n} योजना(एँ) आपके लिए उपयोगी हो सकती हैं; {now} आपकी वर्तमान अवस्था के अनुकूल हैं।",
        "disclaimer": "ये संभावित रूप से उपयोगी योजनाएँ हैं, स्वीकृति नहीं। अंतिम पात्रता और लाभ सरकारी विभाग तय करता है। आवेदन केवल आधिकारिक पेज से ही करें।",
        "verified": "अंतिम सत्यापन", "not_verified": "अभी सत्यापित नहीं", "login": "योजना सहायक के लिए कृपया किसान के रूप में लॉगिन करें।",
        "no_profile": "अपनी योजनाएँ देखने के लिए ऊपर का फ़ॉर्म भरें।", "none": "कोई नहीं",
    },
    "mr": {
        "title": "सरकारी योजना सहाय्यक", "intro": "तुमच्या शेतीबद्दल माहिती द्या. एजंट प्रत्येक योजनेचे पात्रता नियम तपासून तुमच्यासाठी उपयुक्त योजना समजावून सांगेल. कोणताही ओळख क्रमांक घेतला जात नाही.",
        "state": "राज्य", "district": "जिल्हा", "land": "तुम्ही किती जमीन कसता (हेक्टर)", "owns": "जमीन तुमच्या नावावर आहे का?",
        "yes": "होय", "no": "नाही", "ftype": "शेतकरी प्रकार", "owner": "स्वतः कसणारा मालक", "tenant": "भाडेकरू शेतकरी",
        "sharecropper": "वाटेकरी", "stage": "हळद शेतीची सध्याची अवस्था", "docs_have": "तुमच्याकडे असलेल्या कागदपत्रांवर खूण करा",
        "language": "भाषा", "save": "जतन करा आणि योजना शोधा", "select": "— निवडा —",
        "results": "तुमच्या योजना", "match": "पात्र असू शकता", "unknown": "अधिक माहिती हवी", "no_match": "तुमच्या उत्तरांशी जुळत नाही",
        "now": "तुमच्या सध्याच्या अवस्थेस योग्य", "later": "या अवस्थेत उपयुक्त:", "docs_count": "तुमच्याकडे कागदपत्रे: {have}/{need}",
        "missing": "अजून हवे:", "all_docs": "यादीतील सर्व कागदपत्रे तुमच्याकडे आहेत.", "highlights": "मुख्य मुद्दे", "steps": "अर्ज कसा करावा",
        "apply": "अर्जासाठी अधिकृत पान उघडा", "why": "कारण", "calendar": "तुमचे कृती-कॅलेंडर",
        "summary": "{n} योजना तुमच्यासाठी उपयुक्त असू शकतात; {now} तुमच्या सध्याच्या अवस्थेस योग्य आहेत.",
        "disclaimer": "या संभाव्य उपयुक्त योजना आहेत, मंजुरी नाही. अंतिम पात्रता व लाभ शासकीय विभाग ठरवतो. अर्ज फक्त अधिकृत पानावरूनच करा.",
        "verified": "शेवटची पडताळणी", "not_verified": "अजून पडताळणी नाही", "login": "योजना सहाय्यकासाठी कृपया शेतकरी म्हणून लॉगिन करा.",
        "no_profile": "तुमच्या योजना पाहण्यासाठी वरील फॉर्म भरा.", "none": "काहीही नाही",
    },
}

# Localised verdict for each rule check:  CHECK_T[lang][check label][True/False/None]
_L = {
    "State": ("State", "राज्य", "राज्य"),
    "Owns agricultural land": ("Land ownership", "ज़मीन का स्वामित्व", "जमिनीची मालकी"),
    "Minimum landholding": ("Minimum land", "न्यूनतम ज़मीन", "किमान जमीन"),
    "Maximum landholding": ("Maximum land", "अधिकतम ज़मीन", "कमाल जमीन"),
    "Farmer category": ("Farmer category", "किसान श्रेणी", "शेतकरी प्रकार"),
}
_V = {  # result -> (en, hi, mr)
    True: ("meets the rule", "नियम पूरा करता है", "नियम पूर्ण होतो"),
    False: ("does not meet the rule", "नियम पूरा नहीं करता", "नियम पूर्ण होत नाही"),
    None: ("please provide this information", "कृपया यह जानकारी दें", "कृपया ही माहिती द्या"),
}


def check_text(label, result, lang):
    i = {"en": 0, "hi": 1, "mr": 2}[lang]
    name = _L.get(label, (label, label, label))[i]
    return f"{name}: {_V[result][i]}"


def tr(lang):
    return T.get(lang, T["en"])


def fmt(lang, key, **kw):
    return tr(lang)[key].format(**kw)
