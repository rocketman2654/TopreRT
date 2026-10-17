"""Offline payload proposal only. No HID, firmware patching or assigned command."""
from dataclasses import dataclass
import struct
import zlib

MAGIC = b"TRID"
SIZE = 24
# Local proposal identifiers, not USB PID values or allocated wire commands.
PRODUCT_STOCK = {1: 1, 2: 2}  # HHKB PD-KB800W A0.48, R3SB A0.12
FAMILIES = {1: "rt_only", 2: "hold"}
SUPPORTED_COMBINATIONS = {(1, 1), (1, 2), (2, 1)}


@dataclass(frozen=True)
class Identity:
    product: int
    stock: int
    family: str
    build_id: int


def parse(payload, *, expected_product):
    """Parse one exact payload; build IDs do not imply known release versions."""
    if not isinstance(payload, bytes) or len(payload) != SIZE:
        raise ValueError("identity_payload_length")
    magic, major, minor, size, product, family, reserved, stock, build_id, spare, checksum = struct.unpack("<4s6BHIII", payload)
    if magic != MAGIC or (major, minor, size) != (1, 0, SIZE):
        raise ValueError("unsupported_identity_layout")
    if reserved or spare:
        raise ValueError("unsupported_identity_fields")
    if type(expected_product) is not int or expected_product not in PRODUCT_STOCK or product != expected_product:
        raise ValueError("identity_product_mismatch")
    if stock != PRODUCT_STOCK[product] or (product, family) not in SUPPORTED_COMBINATIONS or build_id == 0:
        raise ValueError("unsupported_identity_values")
    if checksum != zlib.crc32(payload[:20]):
        raise ValueError("identity_checksum")
    return Identity(product, stock, FAMILIES[family], build_id)


def encode_fixture(*, product=1, family=1, build_id=1):
    """Synthetic test data, not a firmware image or a device response."""
    body = struct.pack("<4s6BHII", MAGIC, 1, 0, SIZE, product, family, 0,
                       PRODUCT_STOCK[product], build_id, 0)
    return body + struct.pack("<I", zlib.crc32(body))


def encode_identity(identity):
    """Encode a validated build claim; this does not create firmware or allocate IDs."""
    if (type(identity) is not Identity or type(identity.product) is not int
            or type(identity.stock) is not int or type(identity.family) is not str
            or type(identity.build_id) is not int or not 0 < identity.build_id <= 0xFFFFFFFF):
        raise ValueError('identity_encoder_values')
    family = next((number for number, name in FAMILIES.items() if name == identity.family), None)
    if (identity.product not in PRODUCT_STOCK or identity.stock != PRODUCT_STOCK[identity.product]
            or (identity.product, family) not in SUPPORTED_COMBINATIONS):
        raise ValueError('identity_encoder_target')
    payload = encode_fixture(product=identity.product, family=family, build_id=identity.build_id)
    if parse(payload, expected_product=identity.product) != identity:
        raise ValueError('identity_encoder_roundtrip')
    return payload
