from solution.encryption import (
    encrypt_text,
    decrypt_text,
    phone_lookup_hash,
)


def test_encryption_hides_plaintext():
    original = "Pushpak Sharma"
    encrypted = encrypt_text(original)

    assert encrypted != original
    assert original not in encrypted
    assert decrypt_text(encrypted) == original


def test_same_phone_has_same_lookup_hash():
    phone = "+919876543210"

    assert phone_lookup_hash(phone) == phone_lookup_hash(phone)


def test_different_phones_have_different_hashes():
    assert phone_lookup_hash("+919876543210") != phone_lookup_hash(
        "+918765432109"
    )


def test_encryption_uses_randomized_ciphertext():
    first = encrypt_text("9876543210")
    second = encrypt_text("9876543210")

    assert first != second
    assert decrypt_text(first) == decrypt_text(second) == "9876543210"
