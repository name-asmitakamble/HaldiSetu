"""Shared access-control helpers: login/role decorators, verification gate, audit log."""
from functools import wraps

from flask import abort, flash, g, redirect, request, url_for

from models import db
from models_market import AuditLog, UserProof


def login_required(roles=None):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not g.user:
                flash("Please log in to continue.", "warn")
                return redirect(url_for("login", next=request.path))
            if roles and g.user.role not in roles:
                abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco


def is_verified(user):
    if not user:
        return False
    if user.role == "admin":
        return True
    return UserProof.query.filter_by(user_id=user.user_id, status="approved").first() is not None


def verified_required(fn):
    """Posting lots/demands, responding and dealing need admin-approved proof (project plan: humans approve)."""
    @wraps(fn)
    def wrapper(*a, **kw):
        if not is_verified(g.user):
            flash("Your account must be verified by the admin first. Upload your proof under Verification.", "warn")
            return redirect(url_for("dash.verification"))
        return fn(*a, **kw)
    return wrapper


def audit(action, entity=None, entity_id=None, detail=None):
    """Adds an audit row to the session; the caller commits."""
    db.session.add(AuditLog(actor_id=g.user.user_id if g.get("user") else None, action=action,
                            entity=entity, entity_id=entity_id, detail=(detail or "")[:300] or None))
