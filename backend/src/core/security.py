"""
Security Engine: AES-256-GCM Field Encryption, Bcrypt Password Hashing,
JWT Access Tokens, Opaque Refresh Tokens, and Prompt Injection Framing.
"""

import asyncio
import base64
import hashlib
import hmac
import html
import os
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.core.config import settings


# ============================================================================
# 1. FIELD-LEVEL ENCRYPTION AT REST (AES-256-GCM with Authenticated Encryption)
# ============================================================================
def get_aes_gcm_cipher() -> AESGCM:
    key_bytes = base64.b64decode(settings.APPLICATION_ENCRYPTION_KEY_B64, validate=True)
    if len(key_bytes) != 32:
        raise ValueError("APPLICATION_ENCRYPTION_KEY_B64 must decode to exactly 32 bytes (256 bits)")
    return AESGCM(key_bytes)


def encrypt_field(plaintext: str, associated_data: bytes | None = None) -> bytes:
    """
    Encrypts sensitive text using AES-256-GCM with a fresh 12-byte nonce per encryption.
    Prepends the 12-byte nonce to the ciphertext+tag payload.
    """
    if not plaintext:
        return b""
    cipher = get_aes_gcm_cipher()
    nonce = os.urandom(12)
    ciphertext = cipher.encrypt(nonce, plaintext.encode("utf-8"), associated_data)
    return nonce + ciphertext


def decrypt_field(encrypted_bytes: bytes, associated_data: bytes | None = None) -> str:
    """
    Decrypts AES-256-GCM payload, verifying authenticity tag and optional AAD.
    """
    if not encrypted_bytes or len(encrypted_bytes) < 28:
        return ""
    cipher = get_aes_gcm_cipher()
    nonce = encrypted_bytes[:12]
    ciphertext = encrypted_bytes[12:]
    decrypted = cipher.decrypt(nonce, ciphertext, associated_data)
    return decrypted.decode("utf-8")


# ============================================================================
# 2. PASSWORD HASHING (Bcrypt cost 12, non-blocking async wrappers)
# ============================================================================
def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password or not hashed_password:
        return False
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    return await asyncio.to_thread(verify_password, plain_password, hashed_password)


async def get_password_hash_async(password: str) -> str:
    return await asyncio.to_thread(get_password_hash, password)


# ============================================================================
# 3. JWT ACCESS TOKENS & OPAQUE REFRESH TOKENS
# ============================================================================
def create_access_token(
    user_id: str,
    tenant_id: str,
    role: str,
    email: str = "",
    full_name: str = "",
    team_id: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))

    to_encode: dict[str, Any] = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "email": email,
        "name": full_name,
        "team_id": team_id,
        "type": "access",
        "jti": str(uuid.uuid4()),
        "exp": expire,
        "iat": now,
        "iss": "enterprise-crm-auth",
    }
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer="enterprise-crm-auth",
        )
    except jwt.PyJWTError as exc:
        raise ValueError(f"Invalid or expired security token: {exc}") from exc

    if payload.get("type") != "access":
        raise ValueError("Invalid token type: expected access token")

    return payload


def generate_refresh_token() -> str:
    """Generates a 384-bit cryptographically random opaque refresh token."""
    return secrets.token_urlsafe(48)


def hash_token(raw_token: str) -> str:
    """Returns SHA-256 hex digest for storing opaque refresh tokens without plaintext."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# ============================================================================
# 4. PROMPT INJECTION SANITIZATION & BOUNDARY FRAMING (OWASP LLM01)
# ============================================================================
CANONICAL_CRM_XML_TAG = "crm_interaction_content"
_CANONICAL_TAG_RE = re.compile(rf"</?{CANONICAL_CRM_XML_TAG}\s*>", re.IGNORECASE)
_SYSTEM_TAG_RE = re.compile(r"</?system\s*>", re.IGNORECASE)

SUSPICIOUS_PROMPT_PATTERNS = [
    re.compile(
        r"(?i)\b(ignore|disregard|forget|override|bypass)\s+(all\s+)?(previous|prior|above|system)\s*(instructions|prompts|rules|directives)?"
    ),
    re.compile(
        r"(?i)\b(you\s+are\s+now|act\s+as)\s+(in\s+)?(developer\s+mode|admin|god\s+mode|unfiltered|jailbroken)"
    ),
    re.compile(
        r"(?i)\b(dump|leak|reveal|export)\s+(all\s+)?(tenant\s+secrets|api\s*keys|passwords|credentials)"
    ),
    re.compile(
        r"(?i)\b(olvida|ignora|descarta|omite|anula)\s+(todas\s+las\s+)?(instrucciones|indicaciones|reglas)\s*(previas|anteriores)?"
    ),
    re.compile(
        r"(?i)\b(ahora\s+eres|act[uú]a\s+como)\s+(en\s+)?(modo\s+desarrollador|administrador|modo\s+sin\s+restricciones)"
    ),
    re.compile(
        r"(?i)\b(muestra|revela|extrae|filtra)\s+(todos\s+los\s+)?(secretos|claves|contrase[ñn]as|tokens)"
    ),
    re.compile(r"(?i)(<\|im_start\|>|<\|endoftext\|>|\[INST\]|<system>|system\s*:)"),
]


def sanitize_user_input_for_llm(raw_text: str) -> tuple[str, bool]:
    """
    Sanitizes untrusted CRM interaction notes before placing them inside XML boundaries.
    1. Flags known override/exfiltration heuristics for `ai_audit_logs.is_safe_eval`.
    2. Strips framing tags case-insensitively.
    3. Applies `html.escape()` so untrusted input cannot break XML context delimiters.
    """
    if not raw_text:
        return "", False

    is_suspicious = any(pattern.search(raw_text) for pattern in SUSPICIOUS_PROMPT_PATTERNS)

    cleaned = _CANONICAL_TAG_RE.sub("", raw_text)
    cleaned = _SYSTEM_TAG_RE.sub("", cleaned)
    cleaned = html.escape(cleaned)

    return cleaned, is_suspicious
