"""At-rest encryption for OAuth tokens.

feedback.db is a plain SQLite file with no encryption of its own, and it already
holds real briefs (names, venues). Access and refresh tokens are a step up in
sensitivity from that — an access token IS the account, not a description of an
event — so they never touch the database as plaintext.

Key lives in its own gitignored file, not in .env: .env is routinely pasted into
chat, screenshots and `cat` output while debugging; a file nothing else has a
reason to open is a smaller blast radius for the one secret that can act as the
LinkedIn/Instagram account, not just describe it.
"""
import os
import stat

from cryptography.fernet import Fernet, InvalidToken

KEY_PATH = os.environ.get("OAUTH_KEY_PATH", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".oauth_key"))


def _load_or_create_key() -> bytes:
    if os.path.exists(KEY_PATH):
        with open(KEY_PATH, "rb") as f:
            key = f.read().strip()
        if not key:
            raise RuntimeError(f"{KEY_PATH} exists but is empty")
        return key
    key = Fernet.generate_key()
    # O_EXCL: refuse to clobber a key that appeared between the exists() check
    # and here — losing this file makes every stored token permanently
    # undecryptable, so the failure mode for a race is "crash", not "silently
    # re-encrypt everything under a second key nobody has a backup of".
    fd = os.open(KEY_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key)
    os.chmod(KEY_PATH, stat.S_IRUSR | stat.S_IWUSR)  # 0600, belt-and-suspenders vs umask
    return key


_fernet: Fernet | None = None


def _f() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_or_create_key())
    return _fernet


def encrypt(plaintext: str) -> bytes:
    if plaintext is None:
        return None
    return _f().encrypt(plaintext.encode("utf-8"))


def decrypt(token: bytes) -> str:
    """Raises ValueError (not the cryptography-specific exception) on a token
    that doesn't decrypt under the current key — wrong key file, corrupted row,
    or someone hand-edited the database. Callers should treat this as "this
    account's tokens are gone, reconnect it," not retry."""
    if token is None:
        return None
    try:
        return _f().decrypt(bytes(token)).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("token does not decrypt under the current OAuth key") from e
