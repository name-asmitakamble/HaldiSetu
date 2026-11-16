"""Small blueprint so the UI can show agent notifications, proposals and the audit log.
Register in app.py:  from agent_routes import agent_bp ; app.register_blueprint(agent_bp)

CHANGE: current_user_id() must return the logged-in user's id in YOUR auth system.
"""
from flask import Blueprint, abort, g, jsonify, session

from models import db  # adjust if needed
import agent_tools as T
from models_agent import AgentNotification, MatchProposal, AgentRun, AgentAction

agent_bp = Blueprint("agent_bp", __name__, url_prefix="/agent")

 
def current_user_id():
    uid = session.get("uid")
    if not uid:
        abort(401)
    return uid

 
@agent_bp.get("/notifications")
def my_notifications():
    uid = current_user_id()
    items = AgentNotification.query.filter_by(user_id=uid).order_by(AgentNotification.created_at.desc()).limit(30)
    return jsonify([{"id": n.id, "message": n.message, "kind": n.kind, "read": n.is_read,
                     "at": n.created_at.isoformat()} for n in items])

 
@agent_bp.post("/notifications/<int:nid>/read")
def mark_read(nid):
    n = AgentNotification.query.filter_by(id=nid, user_id=current_user_id()).first_or_404()
    n.is_read = True
    db.session.commit()
    return jsonify({"ok": True})

 
@agent_bp.get("/proposals")
def my_proposals():
    """Proposals for the current user. Adapt the owner check to your Lot/Requirement models."""
    uid = current_user_id()
    out = []
    for p in MatchProposal.query.filter_by(status="proposed").order_by(MatchProposal.score.desc()):
        lot, req = db.session.get(T.Lot, p.lot_id), db.session.get(T.Requirement, p.requirement_id)
        if lot and req and uid in (lot.farmer_id, req.buyer_id):
            out.append({"id": p.id, "lot_id": p.lot_id, "requirement_id": p.requirement_id,
                        "score": p.score, "breakdown": p.breakdown_dict(), "explanation": p.explanation})
    return jsonify(out)

 
@agent_bp.post("/proposals/<int:pid>/dismiss")
def dismiss(pid):
    p = db.get_or_404(MatchProposal, pid)
    lot, req = db.session.get(T.Lot, p.lot_id), db.session.get(T.Requirement, p.requirement_id)
    if not lot or not req or current_user_id() not in (lot.farmer_id, req.buyer_id):
        abort(403)
    p.status = "dismissed"
    db.session.commit()
    return jsonify({"ok": True})

 
@agent_bp.get("/runs")
def runs():
    if not g.get("user") or g.user.role != "admin":
        abort(403)
    rows = AgentRun.query.order_by(AgentRun.started_at.desc()).limit(20).all()
    return jsonify([{"id": r.id, "trigger": r.trigger, "mode": r.mode, "status": r.status,
                     "summary": r.summary,
                     "actions": [{"tool": a.tool_name, "input": a.tool_input, "output": a.tool_output}
                                 for a in AgentAction.query.filter_by(run_id=r.id)]} for r in rows])
 