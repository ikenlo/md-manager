from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class CryptoError(RuntimeError):
    pass


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().encryption_key
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise CryptoError("ENCRYPTION_KEY некоректний — згенеруйте Fernet-ключ") from exc


def encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise CryptoError("Не вдалося розшифрувати — інший ENCRYPTION_KEY?") from exc
