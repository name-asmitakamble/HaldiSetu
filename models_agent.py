"""New tables for the marketplace agent. Uses your existing `db` object.

All table names start with "agent_" so they never clash with existing tables.
CHANGE if needed: the import below must point to where your SQLAlchemy `db` lives.
"""
import json
from datetime import datetime

from models import db  # <-- adjust if `db` is defined elsewhere


class AgentRun(db.Model):
    __tablename__ = "agent_runs"
    id = db.Column(db.Integer, primary_key=True)
    trigger = db.Column(db.String(60))          # new_lot / new_requirement / nightly / stale
    entity_type = db.Column(db.String(20))      # lot / requirement
    entity_id = db.Column(db.Integer)
    mode = db.Column(db.String(20))             # llm / deterministic
    status = db.Column(db.String(20), default="running")  # running / done / failed
    summary = db.Column(db.Text)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime)


class AgentAction(db.Model):
    """Audit log: every tool call the agent makes."""
    __tablename__ = "agent_actions"
    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey("agent_runs.id"))
    tool_name = db.Column(db.String(60))
    tool_input = db.Column(db.Text)
    tool_output = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class MatchProposal(db.Model):
    """A lot <-> requirement match proposed by the agent. Users approve or dismiss it."""
    __tablename__ = "agent_match_proposals"
    id = db.Column(db.Integer, primary_key=True)
    lot_id = db.Column(db.Integer, index=True)
    requirement_id = db.Column(db.Integer, index=True)
    score = db.Column(db.Float)
    breakdown = db.Column(db.Text)              # JSON string
    explanation = db.Column(db.Text)
    status = db.Column(db.String(20), default="proposed")  # proposed / accepted / dismissed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("lot_id", "requirement_id", name="uq_agent_lot_req"),
    )

    def breakdown_dict(self):
        try:
            return json.loads(self.breakdown or "{}")
        except ValueError:
            return {}


class AgentNotification(db.Model):
    __tablename__ = "agent_notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, index=True)
    message = db.Column(db.Text)
    language = db.Column(db.String(10), default="en")
    kind = db.Column(db.String(30), default="agent")
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)