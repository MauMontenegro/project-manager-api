"""Contraseñas: hash scrypt (biblioteca estándar), política mínima y contraseñas temporales."""
import base64
import hashlib
import hmac
import secrets
import string

from app.core.exceptions import BusinessRuleError

# Parámetros de scrypt (≈16 MiB de memoria por cálculo). Van en el hash, así que pueden subirse sin romper los existentes.
_N, _R, _P = 2**14, 8, 1
MIN_LONGITUD = 8
MAX_LONGITUD = 128


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def hashear(password: str) -> str:
    sal = secrets.token_bytes(16)
    clave = hashlib.scrypt(password.encode(), salt=sal, n=_N, r=_R, p=_P, maxmem=64 * 1024 * 1024, dklen=32)
    return f"scrypt${_N}${_R}${_P}${_b64(sal)}${_b64(clave)}"


def verificar(password: str, hash_guardado: str | None) -> bool:
    """Comparación en tiempo constante. Sin hash, calcula uno de todas formas para no revelar qué cuentas existen."""
    if not hash_guardado:
        hashear(password)
        return False
    try:
        _, n, r, p, sal, clave = hash_guardado.split("$")
        calculada = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(sal), n=int(n), r=int(r), p=int(p),
            maxmem=64 * 1024 * 1024, dklen=len(base64.b64decode(clave)),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calculada, base64.b64decode(clave))


def validar_politica(password: str, *, correo: str | None, nombre: str | None) -> None:
    """Mínimo 8 caracteres, con letras y números, y que no sea el correo ni el nombre de la persona."""
    if len(password) < MIN_LONGITUD:
        raise BusinessRuleError(f"La contraseña debe tener al menos {MIN_LONGITUD} caracteres")
    if len(password) > MAX_LONGITUD:
        raise BusinessRuleError(f"La contraseña no puede tener más de {MAX_LONGITUD} caracteres")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise BusinessRuleError("La contraseña debe combinar letras y números")
    texto = password.lower()
    prohibidas = {(correo or "").lower(), (correo or "").lower().split("@")[0], (nombre or "").lower().replace(" ", "")}
    if texto in prohibidas - {""}:
        raise BusinessRuleError("La contraseña no puede ser tu correo ni tu nombre")


def generar_temporal() -> str:
    """12 caracteres sin los que se confunden al dictarlos (0/O, 1/l/I); siempre con letras y números."""
    alfabeto = "".join(c for c in string.ascii_letters + string.digits if c not in "0O1lI")
    while True:
        p = "".join(secrets.choice(alfabeto) for _ in range(12))
        if any(c.isalpha() for c in p) and any(c.isdigit() for c in p):
            return p
