"""Simple credentials-based authentication for Kids-Control.

Replaces LDAP authentication with database-stored credentials.
Initial admin account is created with username 'admin' and password 'Admin'.
"""
import hashlib
import secrets
from datetime import datetime, timezone


def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    """Hash password with salt using SHA256.
    
    Args:
        password: Plain text password
        salt: Optional salt (generated if not provided)
    
    Returns:
        Tuple of (hashed_password, salt)
    """
    if salt is None:
        salt = secrets.token_hex(16)
    
    pwd_hash = hashlib.sha256(f"{password}{salt}".encode()).hexdigest()
    return pwd_hash, salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """Verify password against stored hash.
    
    Args:
        password: Plain text password to verify
        stored_hash: Stored password hash
        salt: Salt used for hashing
    
    Returns:
        True if password matches, False otherwise
    """
    pwd_hash, _ = hash_password(password, salt)
    return pwd_hash == stored_hash


def authenticate_user(db, username: str, password: str) -> bool:
    """Authenticate user against database.
    
    Args:
        db: Database session
        username: Username to authenticate
        password: Plain text password
    
    Returns:
        True if authentication successful, False otherwise
    """
    from app.db import User
    
    username = username.strip()
    if not username or not password:
        return False
    
    user = db.query(User).filter_by(username=username, is_active=True).first()
    if not user:
        return False
    
    return verify_password(password, user.password_hash, user.password_salt)


def create_initial_admin(db):
    """Create initial admin account if no users exist.
    
    Creates user 'admin' with password 'Admin' if database is empty.
    
    Args:
        db: Database session
    """
    from app.db import User
    
    # Check if any users exist
    existing_users = db.query(User).count()
    if existing_users > 0:
        return
    
    # Create initial admin
    pwd_hash, salt = hash_password("Admin")
    admin = User(
        username="admin",
        display_name="Administrator",
        password_hash=pwd_hash,
        password_salt=salt,
        is_admin=True,
        is_active=True,
        created_at=datetime.now(timezone.utc)
    )
    
    db.add(admin)
    db.commit()
    print("✓ Initial admin account created (username: admin, password: Admin)")
    print("⚠ Please change the default password immediately!")
