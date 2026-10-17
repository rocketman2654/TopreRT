"""Offline metadata-to-catalog resolution. No HID access or firmware output.

Catalog matches describe a firmware's claim; they are not authentication or
readback verification. Local Development recipes are separate from releases.
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from . import codec
from . import usb_string_codec as envelope

HERE = Path(__file__).resolve().parent
# Only HHKB registration is implemented now. R3SB's proposed payload values
# remain parseable, but do not announce a supported responder or catalog entry.
HHKB_STOCK_SHA256 = '635b995eb5a15aa50c2cedc60da7d8998fcca8285a09d41d984c07fffcaf9d43'
FIXTURE_BUILD_IDS = frozenset((1, 0x12345678))
LEGACY_WITHOUT_METADATA = frozenset(('v0.3.0-rc3', 'v0.3.0-rc4'))
FIELDS = frozenset(('build_id', 'product', 'stock', 'family', 'channel', 'label',
                    'patch_version', 'source_revision', 'recipe_sha256', 'stock_sha256'))
VERSION = r'v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)'


@dataclass(frozen=True)
class Build:
    build_id: int
    product: int
    stock: int
    family: str
    channel: str
    label: str
    patch_version: str | None
    source_revision: str
    recipe_sha256: str
    stock_sha256: str


def _hex(value, size):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{%d}' % size, value) is not None


def validate_catalog(document):
    """Reject the entire catalog on ambiguity/unsupported schema; no last-wins.

    source_revision pins recipe source, not the configurable output image.
    recipe_sha256 pins the separately reviewed recipe manifest's exact bytes.
    Neither a well-formed digest nor a version label proves its provenance.
    """
    if (type(document) is not dict or set(document) != {'schema', 'entries'}
            or type(document['schema']) is not int or document['schema'] != 1
            or type(document['entries']) is not list):
        raise ValueError('catalog_schema')
    builds = []
    seen = set()
    for item in document['entries']:
        if type(item) is not dict or set(item) != FIELDS:
            raise ValueError('catalog_entry_fields')
        identifier = item['build_id']
        if (type(identifier) is not int or not 0 < identifier <= 0xFFFFFFFF
                or identifier in FIXTURE_BUILD_IDS):
            raise ValueError('catalog_build_id')
        if identifier in seen:
            raise ValueError('catalog_duplicate_build_id')
        seen.add(identifier)
        if (type(item['product']) is not int or item['product'] != 1
                or type(item['stock']) is not int or item['stock'] != 1
                or item['stock_sha256'] != HHKB_STOCK_SHA256
                or item['family'] not in ('rt_only', 'hold')):
            raise ValueError('catalog_target')
        channel, version, label = item['channel'], item['patch_version'], item['label']
        if channel not in ('development', 'prerelease', 'release'):
            raise ValueError('catalog_channel')
        if (not isinstance(label, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 ._()+/-]{0,79}', label)):
            raise ValueError('catalog_label')
        if channel == 'development':
            if version is not None or not label.startswith('Development '):
                raise ValueError('catalog_development_version')
        elif (not isinstance(version, str) or len(version) > 48
              or not re.fullmatch(VERSION + (r'-rc[1-9][0-9]*' if channel == 'prerelease' else ''), version)):
            raise ValueError('catalog_patch_version')
        if version in LEGACY_WITHOUT_METADATA:
            raise ValueError('catalog_legacy_without_metadata')
        revision = item['source_revision']
        working_tree = (channel == 'development' and isinstance(revision, str)
                        and revision.startswith('working-tree-sha256:')
                        and _hex(revision[len('working-tree-sha256:'):], 64))
        if not (_hex(revision, 40) or working_tree) or not _hex(item['recipe_sha256'], 64):
            raise ValueError('catalog_provenance_fields')
        builds.append(Build(**item))
    return tuple(builds)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('catalog_duplicate_json_key')
        result[key] = value
    return result


def load_catalog(path=HERE / 'build_catalog.json'):
    """Read a local JSON catalog, rejecting duplicate keys at every level."""
    document = json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=_unique_object)
    validate_catalog(document)
    return document


def _resolve(identity, document):
    builds = validate_catalog(document)
    entry = next((item for item in builds if item.build_id == identity.build_id), None)
    matching = entry is not None and (entry.product, entry.stock, entry.family) == (
        identity.product, identity.stock, identity.family)
    # A globally known ID on a different target/family is inconsistent, not a
    # fallback to the version of that other firmware.
    status = ('registered_build_claim' if matching else
              'catalog_identity_mismatch' if entry is not None else 'unregistered_build_claim')
    digest = hashlib.sha256(json.dumps(document, sort_keys=True, separators=(',', ':'),
                                      ensure_ascii=True).encode('ascii')).hexdigest()
    return {
        'schema': 1, 'scope': 'offline_identity_catalog_resolution', 'status': status,
        'product': identity.product, 'stock': identity.stock, 'claimed_family': identity.family,
        'build_id': identity.build_id, 'catalog_sha256': digest, 'catalog_match': matching,
        'channel': entry.channel if matching else None,
        'build_label': entry.label if matching else None,
        'registered_patch_version': entry.patch_version if matching else None,
        'firmware_authenticated': False, 'image_integrity_verified': False,
        'settings_verified': False, 'device_identity_verified': False,
    }


def resolve_text(text, *, expected_product, catalog_document):
    return _resolve(envelope.parse_text(text, expected_product=expected_product), catalog_document)


def resolve_descriptor(data, *, expected_product, catalog_document):
    return _resolve(envelope.parse_descriptor(data, expected_product=expected_product), catalog_document)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=HERE / 'build_catalog.json')
    parser.add_argument('--text-file', type=Path, help='Exact saved TRID1 text, with no trailing newline')
    parser.add_argument('--expected-product', type=int, choices=sorted(codec.PRODUCT_STOCK), default=1)
    args = parser.parse_args()
    document = load_catalog(args.catalog)
    if args.text_file is None:
        result = {'scope': 'offline_catalog_validation', 'entries': len(validate_catalog(document)),
                  'device_access': False, 'firmware_output': False}
    else:
        result = resolve_text(args.text_file.read_text(encoding='utf-8'),
                              expected_product=args.expected_product, catalog_document=document)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
