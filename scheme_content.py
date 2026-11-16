"""
Multilingual scheme knowledge base used by the scheme agent. Keyed by the English scheme_name in seed.py.

REVIEW CHECKLIST (do before the final demo):
  1. Open each official_url and confirm highlights/steps still match the portal (amounts, dates, portal menus change).
  2. Have a Hindi/Marathi speaker read the text.
  3. Set last_verified_date in seed.py only after (1).
Amounts/percentages are deliberately NOT written here — the text says "check the portal for the current amount".
"""
CONTENT = {
    "PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)": {
        "stages": ["pre_sowing", "sowing", "growing", "harvest", "post_harvest", "selling"],
        "docs": ["aadhaar", "aadhaar_mobile", "bank", "land_record"],
        "names": {"en": "PM-KISAN", "hi": "पीएम-किसान सम्मान निधि", "mr": "पीएम-किसान सन्मान निधी"},
        "highlights": {
            "en": "Income support paid in instalments directly into the bank account of eligible landholding farmer families. It helps with farm expenses and can be applied for at any time of the year. e-KYC is needed to keep receiving instalments.",
            "hi": "पात्र भूमिधारक किसान परिवारों के बैंक खाते में किस्तों में सीधे आर्थिक सहायता दी जाती है। यह खेती के खर्च में मदद करती है और साल में कभी भी आवेदन किया जा सकता है। किस्तें जारी रहने के लिए ई-केवाईसी ज़रूरी है।",
            "mr": "पात्र जमीनधारक शेतकरी कुटुंबांच्या बँक खात्यात हप्त्यांनी थेट आर्थिक मदत दिली जाते. शेतीच्या खर्चात मदत होते आणि वर्षातून कधीही अर्ज करता येतो. हप्ते चालू राहण्यासाठी ई-केवायसी आवश्यक आहे.",
        },
        "steps": {
            "en": ["Open pmkisan.gov.in and choose 'Farmers Corner' → 'New Farmer Registration'.",
                   "Enter Aadhaar number, mobile number and state, then verify the code shown.",
                   "Fill in personal, bank account and land details exactly as in your records.",
                   "Complete e-KYC (OTP on the portal, or biometric at a Common Service Centre).",
                   "Later, use 'Know your status' on the portal to track your instalments."],
            "hi": ["pmkisan.gov.in खोलें और 'Farmers Corner' → 'New Farmer Registration' चुनें।",
                   "आधार नंबर, मोबाइल नंबर और राज्य भरें, फिर दिखाया गया कोड डालें।",
                   "व्यक्तिगत, बैंक खाता और भूमि का विवरण अपने रिकॉर्ड के अनुसार सही भरें।",
                   "ई-केवाईसी पूरा करें (पोर्टल पर OTP से या कॉमन सर्विस सेंटर पर बायोमेट्रिक से)।",
                   "बाद में पोर्टल पर 'Know your status' से किस्तों की स्थिति देखें।"],
            "mr": ["pmkisan.gov.in उघडा आणि 'Farmers Corner' → 'New Farmer Registration' निवडा.",
                   "आधार क्रमांक, मोबाइल क्रमांक आणि राज्य भरा, नंतर दिसणारा कोड टाका.",
                   "वैयक्तिक, बँक खाते आणि जमिनीची माहिती तुमच्या नोंदींनुसार अचूक भरा.",
                   "ई-केवायसी पूर्ण करा (पोर्टलवर OTP ने किंवा कॉमन सर्व्हिस सेंटरवर बायोमेट्रिकने).",
                   "नंतर पोर्टलवरील 'Know your status' मधून हप्त्यांची स्थिती पहा."],
        },
    },
    "PMFBY (Pradhan Mantri Fasal Bima Yojana)": {
        "stages": ["pre_sowing", "sowing"],
        "docs": ["aadhaar", "bank", "land_record", "sowing"],
        "names": {"en": "Crop Insurance (PMFBY)", "hi": "फसल बीमा योजना (पीएमएफबीवाई)", "mr": "पीक विमा योजना (पीएमएफबीवाय)"},
        "highlights": {
            "en": "Insurance cover against crop loss from notified natural causes, at a subsidised farmer premium. Enrolment is only possible before the cut-off date of the season, so apply early. Check that turmeric is notified for your district and season.",
            "hi": "अधिसूचित प्राकृतिक कारणों से फसल नुकसान पर बीमा सुरक्षा, किसान को रियायती प्रीमियम पर। नामांकन सत्र की अंतिम तिथि से पहले ही हो सकता है, इसलिए जल्दी आवेदन करें। देखें कि आपके ज़िले और मौसम में हल्दी अधिसूचित है या नहीं।",
            "mr": "अधिसूचित नैसर्गिक कारणांमुळे पिकाच्या नुकसानीवर विमा संरक्षण, शेतकऱ्यासाठी अनुदानित हप्त्यावर. नोंदणी हंगामाच्या अंतिम तारखेपूर्वीच करता येते, म्हणून लवकर अर्ज करा. तुमच्या जिल्ह्यात आणि हंगामात हळद अधिसूचित आहे का ते तपासा.",
        },
        "steps": {
            "en": ["Ask your bank, Common Service Centre or agriculture office whether turmeric is notified in your district and season, and note the last date.",
                   "Keep your land record, bank passbook, Aadhaar and sowing declaration ready.",
                   "Apply through your bank branch, a CSC, or the Farmer Corner on pmfby.gov.in before the cut-off date.",
                   "Keep the premium receipt / policy details safely.",
                   "If crop loss happens, report it within the time limit in the guidelines (commonly 72 hours) using the channels listed on pmfby.gov.in."],
            "hi": ["अपने बैंक, कॉमन सर्विस सेंटर या कृषि कार्यालय से पूछें कि आपके ज़िले और मौसम में हल्दी अधिसूचित है या नहीं, और अंतिम तिथि नोट करें।",
                   "भूमि अभिलेख, बैंक पासबुक, आधार और बुवाई घोषणा तैयार रखें।",
                   "अंतिम तिथि से पहले बैंक शाखा, सीएससी या pmfby.gov.in के Farmer Corner से आवेदन करें।",
                   "प्रीमियम रसीद / पॉलिसी का विवरण सुरक्षित रखें।",
                   "फसल नुकसान होने पर दिशानिर्देश की समय-सीमा (सामान्यतः 72 घंटे) में pmfby.gov.in पर दिए माध्यमों से सूचना दें।"],
            "mr": ["तुमच्या बँकेत, कॉमन सर्व्हिस सेंटरमध्ये किंवा कृषी कार्यालयात विचारा की तुमच्या जिल्ह्यात आणि हंगामात हळद अधिसूचित आहे का, आणि अंतिम तारीख नोंदवा.",
                   "जमिनीचा उतारा, बँक पासबुक, आधार आणि पेरणी घोषणापत्र तयार ठेवा.",
                   "अंतिम तारखेपूर्वी बँक शाखा, सीएससी किंवा pmfby.gov.in वरील Farmer Corner मधून अर्ज करा.",
                   "हप्त्याची पावती / पॉलिसीचा तपशील जपून ठेवा.",
                   "पिकाचे नुकसान झाल्यास मार्गदर्शक सूचनांतील मुदतीत (साधारणपणे ७२ तास) pmfby.gov.in वर दिलेल्या मार्गांनी कळवा."],
        },
    },
    "Kisan Credit Card (KCC)": {
        "stages": ["pre_sowing", "sowing", "growing"],
        "docs": ["aadhaar", "bank", "land_record", "photo"],
        "names": {"en": "Kisan Credit Card (KCC)", "hi": "किसान क्रेडिट कार्ड (केसीसी)", "mr": "किसान क्रेडिट कार्ड (केसीसी)"},
        "highlights": {
            "en": "Low-cost short-term credit from a bank for seed, rhizomes, fertiliser and other cultivation costs, so you need not borrow from private lenders. Interest benefits may apply for timely repayment — ask your bank.",
            "hi": "बीज/कंद, खाद और अन्य खेती-खर्च के लिए बैंक से कम ब्याज पर अल्पकालिक ऋण, ताकि निजी साहूकार से उधार न लेना पड़े। समय पर चुकाने पर ब्याज में लाभ मिल सकता है — अपने बैंक से पूछें।",
            "mr": "बियाणे/कंद, खते आणि इतर लागवड खर्चासाठी बँकेकडून कमी व्याजाचे अल्प मुदतीचे कर्ज, त्यामुळे खासगी सावकाराकडून कर्ज घ्यावे लागत नाही. वेळेवर परतफेड केल्यास व्याजात सवलत मिळू शकते — तुमच्या बँकेत विचारा.",
        },
        "steps": {
            "en": ["Visit the bank branch where you have your account (or any bank that offers KCC) and ask for the KCC application form.",
                   "Submit the form with identity proof, address proof, land record and photographs.",
                   "The bank checks your land and cropping details and decides the credit limit.",
                   "After sanction you receive the card/passbook and can withdraw within the limit; repay on time.",
                   "See the official page for scheme details and current bank guidelines."],
            "hi": ["जिस बैंक में आपका खाता है (या केसीसी देने वाले किसी भी बैंक) की शाखा में जाकर केसीसी आवेदन फ़ॉर्म माँगें।",
                   "पहचान पत्र, पते का प्रमाण, भूमि अभिलेख और फोटो के साथ फ़ॉर्म जमा करें।",
                   "बैंक आपकी ज़मीन और फसल का विवरण जाँचकर क्रेडिट सीमा तय करता है।",
                   "मंज़ूरी के बाद कार्ड/पासबुक मिलती है; सीमा के भीतर राशि निकालें और समय पर चुकाएँ।",
                   "योजना की जानकारी और बैंक के नवीनतम निर्देश आधिकारिक पेज पर देखें।"],
            "mr": ["ज्या बँकेत तुमचे खाते आहे (किंवा केसीसी देणाऱ्या कोणत्याही बँकेच्या) शाखेत जाऊन केसीसी अर्जाचा नमुना मागा.",
                   "ओळखपत्र, पत्त्याचा पुरावा, जमिनीचा उतारा आणि फोटोंसह अर्ज जमा करा.",
                   "बँक तुमची जमीन आणि पिकांची माहिती तपासून कर्जमर्यादा ठरवते.",
                   "मंजुरीनंतर कार्ड/पासबुक मिळते; मर्यादेत रक्कम काढा आणि वेळेवर परतफेड करा.",
                   "योजनेची माहिती आणि बँकेच्या ताज्या सूचना अधिकृत पानावर पहा."],
        },
    },
    "Agriculture Infrastructure Fund (AIF)": {
        "stages": ["harvest", "post_harvest", "selling"],
        "docs": ["aadhaar", "bank", "land_record", "project_report"],
        "names": {"en": "Agriculture Infrastructure Fund (AIF)", "hi": "कृषि अवसंरचना कोष (एआईएफ)", "mr": "कृषी पायाभूत सुविधा निधी (एआयएफ)"},
        "highlights": {
            "en": "Loans with interest support for post-harvest projects such as turmeric drying yards, boiling/polishing units, warehouses and cold or dry storage. Useful when you want to store and sell later at a better price. A project report is needed.",
            "hi": "हल्दी सुखाने के यार्ड, उबालने/पॉलिश इकाई, गोदाम और भंडारण जैसी कटाई-पश्चात परियोजनाओं के लिए ब्याज सहायता वाला ऋण। बाद में बेहतर भाव पर बेचने के लिए भंडारण करना हो तो उपयोगी। परियोजना रिपोर्ट चाहिए।",
            "mr": "हळद वाळवण्याचे यार्ड, शिजवणे/पॉलिश युनिट, गोदाम आणि साठवण अशा काढणीनंतरच्या प्रकल्पांसाठी व्याज सवलतीसह कर्ज. नंतर चांगल्या भावात विकण्यासाठी साठवण करायची असल्यास उपयुक्त. प्रकल्प अहवाल आवश्यक.",
        },
        "steps": {
            "en": ["Decide your project (for example a drying yard or storage room) and prepare a simple project report with costs.",
                   "Register on the portal agriinfra.dac.gov.in.",
                   "Submit the project and choose a participating bank/lender through the portal.",
                   "The lender appraises the project and sanctions the loan; interest support applies as per the scheme rules.",
                   "Check the portal for the current loan limit, interest support and eligible project types."],
            "hi": ["अपनी परियोजना तय करें (जैसे सुखाने का यार्ड या भंडारण कक्ष) और लागत सहित सरल परियोजना रिपोर्ट बनाएँ।",
                   "पोर्टल agriinfra.dac.gov.in पर पंजीकरण करें।",
                   "परियोजना जमा करें और पोर्टल से सहभागी बैंक/ऋणदाता चुनें।",
                   "ऋणदाता परियोजना का मूल्यांकन कर ऋण मंज़ूर करता है; ब्याज सहायता योजना के नियमों के अनुसार मिलती है।",
                   "वर्तमान ऋण सीमा, ब्याज सहायता और पात्र परियोजनाएँ पोर्टल पर देखें।"],
            "mr": ["तुमचा प्रकल्प ठरवा (उदा. वाळवण्याचे यार्ड किंवा साठवण खोली) आणि खर्चासह साधा प्रकल्प अहवाल तयार करा.",
                   "agriinfra.dac.gov.in पोर्टलवर नोंदणी करा.",
                   "प्रकल्प सादर करा आणि पोर्टलवरून सहभागी बँक/कर्जदाता निवडा.",
                   "कर्जदाता प्रकल्पाचे मूल्यमापन करून कर्ज मंजूर करतो; व्याज सवलत योजनेच्या नियमांनुसार मिळते.",
                   "सध्याची कर्ज मर्यादा, व्याज सवलत आणि पात्र प्रकल्प पोर्टलवर पहा."],
        },
    },
    "PM-FME (PM Formalisation of Micro Food Processing Enterprises)": {
        "stages": ["post_harvest", "selling"],
        "docs": ["aadhaar", "bank", "project_report", "photo"],
        "names": {"en": "PM-FME (micro food processing)", "hi": "पीएम-एफएमई (सूक्ष्म खाद्य प्रसंस्करण)", "mr": "पीएम-एफएमई (सूक्ष्म अन्न प्रक्रिया)"},
        "highlights": {
            "en": "Credit-linked subsidy to set up or upgrade a micro food-processing unit — for turmeric this can mean boiling, polishing or powder making. It is for processing enterprises, not for growing turmeric alone. Check the portal for the current subsidy rate and limit.",
            "hi": "सूक्ष्म खाद्य प्रसंस्करण इकाई शुरू करने या सुधारने के लिए ऋण से जुड़ी सब्सिडी — हल्दी के लिए इसका मतलब उबालना, पॉलिश या पाउडर बनाना हो सकता है। यह प्रसंस्करण उद्यमों के लिए है, केवल हल्दी उगाने के लिए नहीं। वर्तमान सब्सिडी दर और सीमा पोर्टल पर देखें।",
            "mr": "सूक्ष्म अन्न प्रक्रिया युनिट सुरू करण्यासाठी किंवा सुधारण्यासाठी कर्जाशी जोडलेले अनुदान — हळदीसाठी म्हणजे शिजवणे, पॉलिश किंवा पावडर बनवणे. हे प्रक्रिया उद्योगांसाठी आहे, फक्त हळद पिकवण्यासाठी नाही. सध्याचा अनुदान दर व मर्यादा पोर्टलवर पहा.",
        },
        "steps": {
            "en": ["Decide the processing activity (boiling, polishing, powder) and prepare a simple project report.",
                   "Visit pmfme.mofpi.gov.in and check the application options for individuals / groups.",
                   "Submit your application with identity, bank and project details.",
                   "The bank and the state nodal agency review it; subsidy is linked to the bank loan.",
                   "Follow the portal for the current eligibility and subsidy details."],
            "hi": ["प्रसंस्करण गतिविधि तय करें (उबालना, पॉलिश, पाउडर) और सरल परियोजना रिपोर्ट बनाएँ।",
                   "pmfme.mofpi.gov.in पर जाकर व्यक्ति / समूह के लिए आवेदन विकल्प देखें।",
                   "पहचान, बैंक और परियोजना विवरण के साथ आवेदन जमा करें।",
                   "बैंक और राज्य नोडल एजेंसी इसकी समीक्षा करते हैं; सब्सिडी बैंक ऋण से जुड़ी होती है।",
                   "वर्तमान पात्रता और सब्सिडी की जानकारी के लिए पोर्टल देखें।"],
            "mr": ["प्रक्रिया उपक्रम ठरवा (शिजवणे, पॉलिश, पावडर) आणि साधा प्रकल्प अहवाल तयार करा.",
                   "pmfme.mofpi.gov.in वर जाऊन व्यक्ती / गटासाठी अर्जाचे पर्याय पहा.",
                   "ओळख, बँक आणि प्रकल्प तपशीलांसह अर्ज सादर करा.",
                   "बँक आणि राज्य नोडल एजन्सी त्याचा आढावा घेतात; अनुदान बँक कर्जाशी जोडलेले असते.",
                   "सध्याच्या पात्रता व अनुदानाच्या माहितीसाठी पोर्टल पहा."],
        },
    },
}

# APPLY LINKS — where the farmer's "Apply" button goes (the scheme's own application page).
# Click every link once before the demo. If one is wrong, fix only that line.
# A scheme not listed here (or with an empty value) falls back to its official_url.
APPLY_URLS = {
    # CONFIRMED in government-domain search: "New Farmer Registration Form" on pmkisan.gov.in
    "PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)": "https://pmkisan.gov.in/RegistrationFormupdated.aspx",
    # PMFBY has no separate public apply URL: farmers enter through "Farmer Corner" on the portal home page
    "PMFBY (Pradhan Mantri Fasal Bima Yojana)": "https://pmfby.gov.in/",
    # myScheme (Govt of India) page of KCC; the card is issued by a bank/PACS
    "Kisan Credit Card (KCC)": "https://www.myscheme.gov.in/schemes/kcc",
    # CONFIRMED: AIF "User/Beneficiary Login" - borrowers register / log in here to apply
    "Agriculture Infrastructure Fund (AIF)": "https://agriinfra.dac.gov.in/Home/Login",
    # PM-FME official site; its application is made after login, with help from the District Resource Person (DRP)
    "PM-FME (PM Formalisation of Micro Food Processing Enterprises)": "https://pmfme.mofpi.gov.in/sitesubsite/",
}

# Where a portal has no direct public form, tell the farmer exactly what to click / who to meet after the page opens.
APPLY_HINTS = {
    "PMFBY (Pradhan Mantri Fasal Bima Yojana)": {
        "en": "On the portal open \"Farmer Corner\", register / log in with your mobile number, then choose your crop and season. You can also enrol through your bank or a CSC centre before the cut-off date.",
        "mr": "पोर्टलवर \"Farmer Corner\" उघडा, मोबाईल नंबरने नोंदणी / लॉगिन करा आणि पीक व हंगाम निवडा. अंतिम तारखेपूर्वी बँक किंवा CSC केंद्रातूनही नोंदणी करता येते.",
        "hi": "पोर्टल पर \"Farmer Corner\" खोलें, मोबाइल नंबर से पंजीकरण / लॉगिन करें और फसल व मौसम चुनें। अंतिम तिथि से पहले बैंक या CSC केंद्र से भी नामांकन हो सकता है."},
    "Kisan Credit Card (KCC)": {
        "en": "The KCC is issued by your bank branch or PACS. Open this page for the official details, then take the application with your land record and ID proof to your bank.",
        "mr": "KCC तुमची बँक शाखा किंवा PACS देते. अधिकृत माहितीसाठी हे पान उघडा आणि जमिनीचा उतारा व ओळखपत्रासह बँकेत अर्ज द्या.",
        "hi": "KCC आपकी बैंक शाखा या PACS जारी करती है। आधिकारिक जानकारी के लिए यह पेज खोलें और भूमि रिकॉर्ड व पहचान पत्र के साथ बैंक में आवेदन दें."},
    "Agriculture Infrastructure Fund (AIF)": {
        "en": "Register or log in as a Beneficiary, then fill the project application. Keep the portal's Checklist of Documents ready.",
        "mr": "लाभार्थी म्हणून नोंदणी / लॉगिन करा आणि प्रकल्प अर्ज भरा. पोर्टलवरील कागदपत्रांची यादी तयार ठेवा.",
        "hi": "लाभार्थी के रूप में पंजीकरण / लॉगिन करें और प्रोजेक्ट आवेदन भरें। पोर्टल की दस्तावेज़ सूची तैयार रखें."},
    "PM-FME (PM Formalisation of Micro Food Processing Enterprises)": {
        "en": "Use the Login / application option on the site. Your District Resource Person (DRP) or district nodal office can help you apply.",
        "mr": "साइटवरील लॉगिन / अर्ज पर्याय वापरा. जिल्हा संसाधन व्यक्ती (DRP) किंवा जिल्हा नोडल कार्यालय अर्जासाठी मदत करू शकते.",
        "hi": "साइट पर लॉगिन / आवेदन विकल्प का उपयोग करें। जिला संसाधन व्यक्ति (DRP) या जिला नोडल कार्यालय आवेदन में मदद कर सकता है."},
}


def apply_url_for(scheme):
    """Link for the Apply button: the scheme's specific application page, else its official site."""
    return APPLY_URLS.get(scheme.scheme_name) or scheme.official_url


def apply_hint_for(scheme, lang="en"):
    h = APPLY_HINTS.get(scheme.scheme_name)
    return (h.get(lang) or h.get("en")) if h else ""

from more_schemes import APPLY_EXTRA, CONTENT_EXTRA, HINTS_EXTRA  # noqa: E402

CONTENT.update(CONTENT_EXTRA)
APPLY_URLS.update(APPLY_EXTRA)
APPLY_HINTS.update(HINTS_EXTRA)