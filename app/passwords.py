"""Salted password hashes for the parent login and the client setup password."""

from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# argon2id with a modest memory cost so a small household hub (about 256 MB)
# can verify a login without swapping. parallelism=1 avoids assuming many cores.
_HASHER = PasswordHasher(time_cost=3, memory_cost=19456, parallelism=1)


def is_password_hash(value: str) -> bool:
    return (value or "").startswith("$argon2")


def hash_password(plain: str) -> str:
    """Return an argon2id hash. An existing hash is kept as-is."""
    if is_password_hash(plain):
        return plain
    return _HASHER.hash(plain)


def passwords_match(given: str, expected: str) -> bool:
    """True when `given` matches a stored hash or, for legacy values, the plaintext.

    Usernames are still compared on the legacy path. Only values that already
    look like argon2 hashes are verified as passwords.
    """
    if not given or not expected:
        return False
    if is_password_hash(expected):
        try:
            return bool(_HASHER.verify(expected, given))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
    return secrets.compare_digest(
        hashlib.sha256(given.encode("utf-8")).digest(),
        hashlib.sha256(expected.encode("utf-8")).digest(),
    )
