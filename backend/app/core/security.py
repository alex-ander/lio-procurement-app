from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# bcrypt operates on at most 72 bytes; longer inputs are truncated (its
# standard behaviour). We truncate explicitly so hashing never raises.
_BCRYPT_MAX_BYTES = 72


def _to_bcrypt_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(_to_bcrypt_bytes(password), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            _to_bcrypt_bytes(plain_password), hashed_password.encode("utf-8")
        )
    except ValueError:
        # Malformed/invalid stored hash.
        return False


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    """Create a signed JWT whose ``sub`` claim is the user id."""
    expire_minutes = expires_minutes or settings.access_token_expire_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str | None:
    """Return the subject (user id) from a valid token, or ``None`` if invalid."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except JWTError:
        return None
    return payload.get("sub")
