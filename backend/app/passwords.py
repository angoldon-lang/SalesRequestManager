"""Hash delle password con scrypt (libreria standard, nessuna dipendenza esterna)."""
import base64
import hashlib
import hmac
import secrets

N, R, P = 2 ** 14, 8, 1
MIN_LENGTH = 10


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=32)
    return f"scrypt${N}${R}${P}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str | None) -> bool:
    try:
        scheme, n, r, p, salt, dk = (stored or "").split("$")
        if scheme != "scrypt":
            return False
        calc = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt),
                              n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except Exception:
        return False


# Hash di comodo: si verifica comunque una password anche se l'utente non esiste (tempi uniformi)
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def validate_new_password(password: str, *, username: str = "", forbidden: tuple[str, ...] = ()) -> None:
    """Solleva ValueError con un messaggio per l'utente."""
    if len(password) < MIN_LENGTH:
        raise ValueError(f"La password deve avere almeno {MIN_LENGTH} caratteri")
    if len(password) > 128:
        raise ValueError("Password troppo lunga (max 128 caratteri)")
    low = password.lower()
    if username and low == username.lower():
        raise ValueError("La password non può coincidere con il nome utente")
    if any(low == f.lower() for f in forbidden if f):
        raise ValueError("Scegli una password diversa da quella attuale/predefinita")


def generate_password(length: int = 14) -> str:
    alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # senza caratteri ambigui
    return "".join(secrets.choice(alphabet) for _ in range(length))
