"""Create or reset the admin account.   Usage:  python make_admin.py 9000000000 YourNewPassword
Then log in at http://127.0.0.1:5000/login/admin"""
import sys

from app import create_app
from models import User, db

if len(sys.argv) != 3 or len(sys.argv[2]) < 8:
    sys.exit("Usage: python make_admin.py <10-digit-phone> <password of at least 8 characters>")
phone, pw = sys.argv[1], sys.argv[2]
app = create_app()
with app.app_context():
    u = User.query.filter_by(phone=phone).first()
    if u and u.role != "admin":
        sys.exit(f"{phone} is already a {u.role} account. Use a different phone number for the admin.")
    if not u:
        u = User(name="Administrator", role="admin", phone=phone)
        db.session.add(u)
    u.set_password(pw)
    db.session.commit()
    print(f"Admin ready. Log in at /login/admin with phone {phone} and the password you gave.")
