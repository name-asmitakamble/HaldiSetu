"""
Proof agent: reads an uploaded proof (land record / business licence) and RAISES FLAGS for the admin.
It never approves or rejects — the admin decides (project plan: "AI never verifies a user alone").

  basic mode : file checks only (size, PDF/image) + a reminder that the admin must read the document
  llm mode   : Claude reads the image and returns name + document type; mismatches are flagged
The result is stored in ProofAnalysis and shown beside the proof in Admin -> Verifications.
"""
import io
import json
from difflib import SequenceMatcher

from PIL import Image

import llm
from models import db
from models_market import ProofAnalysis

MEDIA = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}
EXPECTED = {"farmer": {"land_record", "other"}, "buyer": {"business_licence", "gst", "fssai", "other"}}
SYSTEM = ("You read an Indian document image for a verification assistant. Reply with ONLY JSON: "
          '{"name": <person or business name printed on it, or null>, "document_type": '
          '"land_record"|"business_licence"|"gst"|"fssai"|"id"|"other"|"unreadable", "notes": <short remark or null>}. '
          "Do not guess. If the text is not legible use \"unreadable\".")


def _similar(a, b):
    norm = lambda s: " ".join(sorted((s or "").lower().replace(".", " ").split()))
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def analyze(path, ext, user):
    flags, name, dtype, mode = [], None, None, "basic"
    if ext == "pdf":
        flags.append("PDF: not read automatically — the admin must open and read it.")
    else:
        data = open(path, "rb").read()
        try:
            if min(Image.open(io.BytesIO(data)).size) < 400:
                flags.append("Image is small; text may be hard to read.")
        except Exception:  # noqa: BLE001
            flags.append("Image could not be opened for checks.")
        res = llm.complete_json(SYSTEM, "Read this document.", image=(MEDIA[ext], data)) if llm.available() else None
        if res:
            mode, name, dtype = "llm", (res.get("name") or None), res.get("document_type")
            if dtype == "unreadable":
                flags.append("The document could not be read — ask the user for a clearer photo.")
            elif dtype and dtype not in EXPECTED.get(user.role, set()) | {"other"}:
                flags.append(f"Document looks like '{dtype}', which is unusual for a {user.role}.")
            if name and _similar(name, user.name) < 0.6:
                flags.append(f"Name on the document ('{name}') differs from the account name ('{user.name}').")
            if res.get("notes"):
                flags.append(f"Reader's note: {str(res['notes'])[:150]}")
        else:
            flags.append("Automatic reading is off (no ANTHROPIC_API_KEY) or failed — the admin must read the document.")
    return {"name": name, "type": dtype, "flags": flags, "mode": mode}


def record(proof, path, ext, user):
    """Create/replace the ProofAnalysis for an UserProof (already flushed so it has an id)."""
    r = analyze(path, ext, user)
    row = ProofAnalysis.query.filter_by(proof_id=proof.proof_id).first() or ProofAnalysis(proof_id=proof.proof_id)
    row.extracted_name, row.extracted_type = (r["name"] or None), (r["type"] or None)
    row.flags, row.mode = json.dumps(r["flags"]), r["mode"]
    db.session.add(row)
    return r
