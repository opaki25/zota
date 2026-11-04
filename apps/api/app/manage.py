import argparse
import getpass
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import select
from .db import SessionLocal
from .models import User
from .main import passwords

parser = argparse.ArgumentParser(description='Create a Zota team account')
parser.add_argument('email')
parser.add_argument('--role', choices=['admin', 'editor', 'viewer'], default='admin')
args = parser.parse_args()
email = str(TypeAdapter(EmailStr).validate_python(args.email)).lower()
password = getpass.getpass('Password (at least 12 characters): ')
if len(password) < 12:
    raise SystemExit('Password must have at least 12 characters')
with SessionLocal() as db:
    if db.scalar(select(User).where(User.email == email)):
        raise SystemExit('User already exists')
    db.add(User(email=email, password_hash=passwords.hash(password), role=args.role))
    db.commit()
print('Account created')
