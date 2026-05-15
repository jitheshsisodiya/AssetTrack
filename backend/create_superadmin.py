"""One-time script to create the Super Admin user (Jithesh)."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal
from app.models.models import Institution, User
from app.auth.jwt import hash_password

db = SessionLocal()
try:
    existing = db.query(User).filter(User.username == "Jithesh", User.role == "SuperAdmin").first()
    if existing:
        print("Super admin 'Jithesh' already exists.")
    else:
        inst = Institution(name="System")
        db.add(inst)
        db.flush()
        user = User(
            institution_id=inst.id,
            username="Jithesh",
            password_hash=hash_password("1234"),
            role="SuperAdmin",
        )
        db.add(user)
        db.commit()
        print(f"Super admin created — Username: Jithesh | Password: 1234 | Institution ID: {inst.id}")
finally:
    db.close()
