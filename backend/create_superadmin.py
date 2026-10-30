"""Creates the Super Admin login, or resets its password with --reset.

Usage (from the backend folder):
    python create_superadmin.py            # create (asks for a password)
    python create_superadmin.py --reset    # change the password of the existing Super Admin

Set SUPERADMIN_USERNAME / SUPERADMIN_PASSWORD to run it without prompts.
"""
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal
from app.models.models import Institution, User
from app.auth.jwt import hash_password, username_taken

username = os.environ.get("SUPERADMIN_USERNAME") or input("Super Admin username [Jithesh]: ").strip() or "Jithesh"
password = os.environ.get("SUPERADMIN_PASSWORD") or getpass.getpass("Super Admin password (at least 8 characters): ")
if len(password) < 8:
    sys.exit("The password must be at least 8 characters.")

db = SessionLocal()
try:
    existing = db.query(User).filter(User.username == username, User.role == "SuperAdmin").first()
    if existing:
        if "--reset" in sys.argv:
            existing.password_hash = hash_password(password)
            db.commit()
            print(f"Password updated for Super Admin '{username}'.")
        else:
            print(f"Super Admin '{username}' already exists. Run with --reset to change its password.")
    elif username_taken(db, username):
        sys.exit(f"The username '{username}' is already used by another account.")
    else:
        inst = db.query(Institution).filter(Institution.name == "System").first()
        if not inst:
            inst = Institution(name="System")
            db.add(inst)
            db.flush()
        db.add(User(institution_id=inst.id, username=username, password_hash=hash_password(password), role="SuperAdmin"))
        db.commit()
        print(f"Super Admin '{username}' created.")
finally:
    db.close()
