
"""Create or reset a user.

Usage:
    python create_user.py <username> <password> [admin|staff|viewer]
"""

import re
import sys
from werkzeug.security import generate_password_hash
from app import run_query, ROLES

if len(sys.argv) not in (3, 4):
    sys.exit(__doc__)

username = sys.argv[1].strip()
password = sys.argv[2]
role = sys.argv[3].lower() if len(sys.argv) == 4 else "viewer"

if not re.fullmatch(r"[A-Za-z0-9_.-]{3,30}", username):
    sys.exit("Username must be 3-30 characters (letters, numbers, _, . or -).")

if len(password) < 8:
    sys.exit("Password must contain at least 8 characters.")

if role not in ROLES:
    sys.exit("Role must be one of: " + ", ".join(ROLES))

password_hash = generate_password_hash(password)

existing = run_query(
    "SELECT id FROM users WHERE username = %s",
    (username,)
)

if existing:
    run_query(
        "UPDATE users SET password_hash = %s, role = %s WHERE username = %s",
        (password_hash, role, username),
        fetch=None
    )
    print(f"User '{username}' updated successfully with role '{role}'.")
else:
    run_query(
        "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
        (username, password_hash, role),
        fetch=None
    )
    print(f"User '{username}' created successfully with role '{role}'.")
