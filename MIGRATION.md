# Migration Guide: LDAP to Credentials-Based Authentication

This guide helps you migrate from the LDAP-based authentication system to the new credentials-based authentication.

## What Changed?

### ✅ New System (Credentials-Based)

- **User accounts stored in database** (SQLite)
- **Password hashing** with SHA256 + salt
- **Initial admin account** created automatically:
  - Username: `admin`
  - Password: `Admin`
- **Admin can create additional users** via future UI
- **No LDAP dependency** - simpler deployment

### ❌ Old System (LDAP)

- Required Active Directory/LDAP server
- Complex configuration
- External dependency
- Group membership checks

## Migration Steps

### 1. Backup Your Data

```bash
cd /opt/kids-control/app/data
cp kidscontrol.sqlite3 kidscontrol.sqlite3.backup
```

### 2. Update Code

```bash
cd /opt/kids-control
git fetch origin
git checkout Perplexity-Merge
```

### 3. Update Environment Variables

Edit your `.env` or systemd service file:

**Remove these variables:**
```bash
LDAP_URI
LDAP_BASE_DN
LDAP_REALM
LDAP_PARENT_GROUP_CN
KIDSCONTROL_ADMIN_USER
KIDSCONTROL_ADMIN_PASSWORD
```

**Keep these (optional):**
```bash
KIDSCONTROL_SECRET=your-secret-key
KIDSCONTROL_CHILD_VIEW_TOKEN=optional-token
KIDSCONTROL_WIDGET_TOKEN=optional-token
```

### 4. Database Migration

The new `User` table will be created automatically on first startup.

**Option A: Automatic (Fresh Start)**
```bash
# The system will create the initial admin account automatically
sudo systemctl restart kidscontrol
```

The initial admin account will be:
- **Username:** `admin`
- **Password:** `Admin`

**⚠️ IMPORTANT:** Change this password immediately after first login!

**Option B: Manual (Preserve Existing Admin)**

If you want to keep your existing admin username:

```python
# Run this Python script once
from app.db import SessionLocal, User, Base, engine
from app.auth import hash_password
from datetime import datetime, timezone

Base.metadata.create_all(engine)
db = SessionLocal()

# Create your admin user
pwd_hash, salt = hash_password("YourSecurePassword")
admin = User(
    username="your-admin-name",  # Your preferred admin username
    display_name="Administrator",
    password_hash=pwd_hash,
    password_salt=salt,
    is_admin=True,
    is_active=True,
    created_at=datetime.now(timezone.utc)
)

db.add(admin)
db.commit()
db.close()
print("✓ Admin user created")
```

### 5. Restart Service

```bash
sudo systemctl restart kidscontrol
sudo systemctl status kidscontrol
```

### 6. Test Login

1. Open browser: `http://your-server:8000/login`
2. Login with:
   - Username: `admin`
   - Password: `Admin`
3. **Immediately change the default password!**

### 7. Verify Functionality

- ✓ Dashboard loads
- ✓ Child controls work
- ✓ Schedule editing works
- ✓ Override buttons work
- ✓ API endpoints respond (`/api/check/username`)

## New Features

### User Management (Coming Soon)

The system now supports multiple admin/parent accounts:

- **is_admin**: Can manage all children and settings
- **is_active**: Account can be disabled without deletion
- **last_login**: Track last login time
- **password_salt**: Unique per user for security

Future UI will allow:
- Creating additional parent accounts
- Managing user permissions
- Password changes
- Account activation/deactivation

## Rollback Plan

If you need to rollback:

```bash
cd /opt/kids-control
git checkout main
cp app/data/kidscontrol.sqlite3.backup app/data/kidscontrol.sqlite3
sudo systemctl restart kidscontrol
```

Restore your LDAP environment variables.

## Security Notes

### Password Security

- Passwords are hashed with SHA256 + unique salt per user
- **Never store plaintext passwords**
- Initial `Admin` password is intentionally simple for first setup
- **Change it immediately** after first login

### Session Security

- Sessions use secure cookies
- `KIDSCONTROL_SECRET` should be a long random string
- Sessions expire on browser close

### Database Security

- SQLite database should be readable only by service account
- Recommended permissions: `chmod 600 kidscontrol.sqlite3`
- Regular backups recommended

## Troubleshooting

### "No users found" error

The initial admin wasn't created. Check logs:
```bash
sudo journalctl -u kidscontrol -n 50
```

Manually create admin user (see Option B above).

### "Invalid credentials" on login

Ensure you're using:
- Username: `admin` (lowercase)
- Password: `Admin` (capital A)

### Database locked

Ensure only one instance is running:
```bash
sudo systemctl stop kidscontrol
lsof /opt/kids-control/app/data/kidscontrol.sqlite3
sudo systemctl start kidscontrol
```

### Import errors

Ensure you pulled the latest code:
```bash
cd /opt/kids-control
git fetch origin
git status
git checkout Perplexity-Merge
```

## Questions?

Contact: rolf_greger@web.de

Or open an issue on GitHub.
