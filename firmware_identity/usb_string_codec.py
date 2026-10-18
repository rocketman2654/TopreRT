"""Offline string-envelope proposal. No HID calls, index or release catalog.

The existing 24-byte identity proposal is carried as strict ASCII hex so a
Windows wchar string API can return it without binary/NUL conversion loss.
This fixture format is not yet an installed firmware protocol.
"""
import re
from . import codec

PREFIX = 'TRID1:'
TEXT_LENGTH = len(PREFIX) + 2 * codec.SIZE
DESCRIPTOR_LENGTH = 2 + 2 * TEXT_LENGTH


def parse_text(text, *, expected_product):
    if not isinstance(text, str) or len(text) != TEXT_LENGTH:
        raise ValueError('identity_string_length')
    if not text.startswith(PREFIX) or not re.fullmatch(r'[0-9A-F]{48}', text[len(PREFIX):]):
        raise ValueError('identity_string_envelope')
    return codec.parse(bytes.fromhex(text[len(PREFIX):]), expected_product=expected_product)


def parse_descriptor(data, *, expected_product):
    """Strict complete-descriptor fixture parser, not short-read assembly."""
    if not isinstance(data, bytes) or len(data) != DESCRIPTOR_LENGTH:
        raise ValueError('identity_descriptor_length')
    if data[:2] != bytes((DESCRIPTOR_LENGTH, 3)):
        raise ValueError('identity_descriptor_header')
    try:
        text = data[2:].decode('utf-16-le', errors='strict')
    except UnicodeError as error:
        raise ValueError('identity_descriptor_encoding') from error
    return parse_text(text, expected_product=expected_product)


def encode_fixture(**kwargs):
    """Synthetic offline bytes only; this does not assign a string index."""
    text = PREFIX + codec.encode_fixture(**kwargs).hex().upper()
    return bytes((DESCRIPTOR_LENGTH, 3)) + text.encode('utf-16-le')


def encode_identity(identity):
    """Build the exact immutable descriptor for one validated identity claim."""
    text = PREFIX + codec.encode_identity(identity).hex().upper()
    return bytes((DESCRIPTOR_LENGTH, 3)) + text.encode('utf-16-le')
