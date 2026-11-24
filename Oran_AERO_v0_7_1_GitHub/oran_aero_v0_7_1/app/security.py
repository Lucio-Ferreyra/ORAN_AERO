"""Creación y verificación segura de contraseñas."""

import hashlib, hmac, os

ITERATIONS = 310_000

def hash_password(password: str) -> str:
    """Genera un hash de contraseña para almacenamiento seguro."""
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${derived.hex()}"

def verify_password(password: str, encoded: str) -> bool:
    """Compara la contraseña ingresada con su hash."""
    try:
        scheme, iterations, salt_hex, hash_hex = encoded.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)).hex()
        return hmac.compare_digest(actual, hash_hex)
    except (ValueError, TypeError):
        return False
