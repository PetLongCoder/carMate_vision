"""Unit tests for user privacy encryption."""
from app.core.crypto import decrypt_field, encrypt_field, is_encrypted, mask_email, mask_phone
from app.services.user_privacy_service import encrypt_phone, find_user_by_phone


def test_encrypt_decrypt_roundtrip():
    plain = "13800138000"
    stored = encrypt_field("phone", plain)
    assert is_encrypted(stored)
    assert stored != plain
    assert decrypt_field("phone", stored) == plain


def test_deterministic_ciphertext():
    a = encrypt_field("phone", "13900139000")
    b = encrypt_field("phone", "13900139000")
    assert a == b


def test_masking():
    assert mask_phone("13800138000") == "138****8000"
    assert mask_email("user@example.com") == "u***r@example.com"


def test_service_encrypt_phone():
    token = encrypt_phone("13700137000")
    assert token is not None
    assert is_encrypted(token)


if __name__ == "__main__":
    test_encrypt_decrypt_roundtrip()
    test_deterministic_ciphertext()
    test_masking()
    test_service_encrypt_phone()
    print("privacy crypto tests passed")
