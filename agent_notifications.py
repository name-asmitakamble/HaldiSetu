"""notify_user(): in-app notification now; add SMS/WhatsApp inside send_external() later.

Every message is stored twice on purpose:
  * AgentNotification : full log of what the AI agent said (JSON API under /agent)
  * Notification      : the table the dashboards already show to farmers/buyers
"""
from models import db
from models_agent import AgentNotification
from models_market import Notification


def send_external(user_id, message):
    """Placeholder for SMS / WhatsApp / push (Twilio, FCM...). Does nothing for now."""
    return False


def notify_user(user_id, message, language="en", kind="agent"):
    n = AgentNotification(user_id=user_id, message=message, language=language, kind=kind)
    db.session.add(n)
    db.session.add(Notification(user_id=user_id, text=message[:300]))
    db.session.commit()
    send_external(user_id, message)
    return {"ok": True, "notification_id": n.id}
