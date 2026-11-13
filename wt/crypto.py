"""Minimal, auditable encryption for sync bundles and exports.

Only the standard library is used (``hashlib.scrypt`` + HMAC-SHA256) so the
portable build needs no extra wheels:

* KDF: scrypt(passphrase, salt, n=2**14, r=8, p=1) -> 32-byte key
* Cipher: ChaCha20 (RFC 7539), 96-bit nonce, counter starts at 1
* MAC: HMAC-SHA256 over header+ciphertext (encrypt-then-MAC, verified first)

File layout (``.wtb``):

    magic  b"WTB1"
    salt   16 bytes
    nonce  12 bytes
    ct     variable
    mac    32 bytes

This is deliberately simple: it protects a bundle sitting in a cloud folder or
on a USB stick. It is not a substitute for BitLocker on the live database.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import struct

MAGIC = b"WTB1"
KDF_SCRYPT = 1
KDF_PBKDF2 = 2
SALT_LEN = 16
NONCE_LEN = 12
MAC_LEN = 32
KDF_N = 2 ** 14
KDF_R = 8
KDF_P = 1
PBKDF2_ROUNDS = 120_000


# -- ChaCha20 ----------------------------------------------------------
def _rotl32(value: int, count: int) -> int:
    return ((value << count) | (value >> (32 - count))) & 0xFFFFFFFF


def _quarter_round(state: list[int], a: int, b: int, c: int, d: int) -> None:
    state[a] = (state[a] + state[b]) & 0xFFFFFFFF
    state[d] ^= state[a]
    state[d] = _rotl32(state[d], 16)

    state[c] = (state[c] + state[d]) & 0xFFFFFFFF
    state[b] ^= state[c]
    state[b] = _rotl32(state[b], 12)

    state[a] = (state[a] + state[b]) & 0xFFFFFFFF
    state[d] ^= state[a]
    state[d] = _rotl32(state[d], 8)

    state[c] = (state[c] + state[d]) & 0xFFFFFFFF
    state[b] ^= state[c]
    state[b] = _rotl32(state[b], 7)


def _block(key: bytes, counter: int, nonce: bytes) -> bytes:
    constants = b"expand 32-byte k"
    state = list(struct.unpack("<4I", constants))
    state += list(struct.unpack("<8I", key))
    state.append(counter & 0xFFFFFFFF)
    state += list(struct.unpack("<3I", nonce))
    working = list(state)
    for _ in range(10):
        _quarter_round(working, 0, 4, 8, 12)
        _quarter_round(working, 1, 5, 9, 13)
        _quarter_round(working, 2, 6, 10, 14)
        _quarter_round(working, 3, 7, 11, 15)
        _quarter_round(working, 0, 5, 10, 15)
        _quarter_round(working, 1, 6, 11, 12)
        _quarter_round(working, 2, 7, 8, 13)
        _quarter_round(working, 3, 4, 9, 14)
    out = [(working[i] + state[i]) & 0xFFFFFFFF for i in range(16)]
    return struct.pack("<16I", *out)


def chacha20_xor(key: bytes, nonce: bytes, data: bytes, counter: int = 1) -> bytes:
    if len(key) != 32:
        raise ValueError("key must be 32 bytes")
    if len(nonce) != NONCE_LEN:
        raise ValueError("nonce must be 12 bytes")
    out = bytearray(len(data))
    offset = 0
    block_no = counter
    while offset < len(data):
        stream = _block(key, block_no, nonce)
        chunk = data[offset:offset + 64]
        for i, byte in enumerate(chunk):
            out[offset + i] = byte ^ stream[i]
        offset += 64
        block_no += 1
    return bytes(out)


# -- key derivation / envelope ----------------------------------------
def _pbkdf2_sha256(passphrase: bytes, salt: bytes, rounds: int, length: int) -> bytes:
    """PBKDF2-HMAC-SHA256 fallback (used when hashlib.scrypt is unavailable)."""
    blocks = []
    for block_index in range(1, (length + 31) // 32 + 1):
        block = hmac.new(passphrase, salt + struct.pack(">I", block_index),
                         hashlib.sha256).digest()
        result = bytearray(block)
        for _ in range(rounds - 1):
            block = hmac.new(passphrase, block, hashlib.sha256).digest()
            for i, byte in enumerate(block):
                result[i] ^= byte
        blocks.append(bytes(result))
    return b"".join(blocks)[:length]


def derive_key(passphrase: str, salt: bytes) -> tuple[bytes, int]:
    """Return (key, kdf_id). scrypt when the runtime has it, else PBKDF2."""
    if not passphrase:
        raise ValueError("passphrase required")
    encoded = passphrase.encode("utf-8")
    try:
        key = hashlib.scrypt(encoded, salt=salt, n=KDF_N, r=KDF_R, p=KDF_P, dklen=32)
        return key, KDF_SCRYPT
    except (AttributeError, ValueError):
        return _pbkdf2_sha256(encoded, salt, PBKDF2_ROUNDS, 32), KDF_PBKDF2


def _key_for(kdf_id: int, passphrase: str, salt: bytes) -> bytes:
    encoded = passphrase.encode("utf-8")
    if kdf_id == KDF_SCRYPT:
        return hashlib.scrypt(encoded, salt=salt, n=KDF_N, r=KDF_R, p=KDF_P, dklen=32)
    if kdf_id == KDF_PBKDF2:
        return _pbkdf2_sha256(encoded, salt, PBKDF2_ROUNDS, 32)
    raise ValueError("unsupported kdf")


def _mac_key(key: bytes) -> bytes:
    return hmac.new(key, b"worktime-mac", hashlib.sha256).digest()


def encrypt_bytes(data: bytes, passphrase: str) -> bytes:
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key, kdf_id = derive_key(passphrase, salt)
    body = MAGIC + bytes([kdf_id]) + salt + nonce + chacha20_xor(key, nonce, data)
    mac = hmac.new(_mac_key(key), body, hashlib.sha256).digest()
    return body + mac


def decrypt_bytes(blob: bytes, passphrase: str) -> bytes:
    if len(blob) < len(MAGIC) + 1 + SALT_LEN + NONCE_LEN + MAC_LEN:
        raise ValueError("bundle too short")
    if not blob.startswith(MAGIC):
        raise ValueError("not a WorkTime encrypted bundle")
    kdf_id = blob[len(MAGIC)]
    header = len(MAGIC) + 1 + SALT_LEN + NONCE_LEN
    body, mac = blob[:-MAC_LEN], blob[-MAC_LEN:]
    salt = blob[len(MAGIC) + 1:len(MAGIC) + 1 + SALT_LEN]
    nonce = blob[len(MAGIC) + 1 + SALT_LEN:header]
    key = _key_for(kdf_id, passphrase, salt)
    expected = hmac.new(_mac_key(key), body, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise ValueError("wrong passphrase or corrupted bundle")
    return chacha20_xor(key, nonce, body[header:])


def is_encrypted(blob: bytes) -> bool:
    return blob.startswith(MAGIC)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
