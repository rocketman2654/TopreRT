"""Reproducible Development builds. No USB, firmware installation or compiler."""
import binascii
import hashlib
import json
from pathlib import Path
import sys

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / 'backends/hhkb'))
import hhkb_toprert_engine_v0_6 as engine
import hhkb_v013_generic_hold_builder_v0_2_rc2 as hold
from . import codec, usb_string_codec as envelope, identity_catalog as catalog

HERE = Path(__file__).resolve().parent
TEMPLATE_SHA = 'd9d7b48653f3534d5cccfc6f399e34a1884de86c6290c823d790b731cf644857'
REVERSED = bytes(int(f'{i:08b}'[::-1], 2) for i in range(256))


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode('ascii')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def crc(data):
    value = binascii.crc_hqx(data.translate(REVERSED), 0xFFFF)
    return int(f'{value:016b}'[::-1], 2)


def refresh(data):
    out = bytearray(data)
    out[2:4] = crc(bytes(out[4:65540])).to_bytes(2, 'little')
    out[:2] = crc(bytes(out[2:])).to_bytes(2, 'little')
    return bytes(out)


def sources():
    paths = [Path(__file__), Path(engine.__file__), Path(hold.__file__),
             Path(hold.HHPATCH.__file__), HERE/'patch_template.json',
             Path(codec.__file__), Path(envelope.__file__)]
    return {p.resolve().relative_to(APP).as_posix(): digest(p.read_bytes()) for p in paths}


def entry_for(recipe):
    data = canonical(recipe)
    sha = digest(data)
    identifier = int.from_bytes(bytes.fromhex(sha)[:4], 'little') | 0x80000000
    if identifier in catalog.FIXTURE_BUILD_IDS:
        raise ValueError('Reserved build ID; review a new recipe revision.')
    entry = {'build_id': identifier, 'product': 1, 'stock': 1, 'family': recipe['family'],
             'channel': 'development', 'label': f'Development HHKB {recipe["family"]} GUI {identifier:08X}',
             'patch_version': None, 'source_revision': 'working-tree-sha256:' + digest(canonical(recipe['sources'])),
             'recipe_sha256': sha, 'stock_sha256': engine.STOCK_SHA256}
    catalog.validate_catalog({'schema': 1, 'entries': [entry]})
    return entry


def normalize_hold(slots):
    hold.validate_slots(slots)
    names = {value: key for key, value in hold.KEY_MAP.items()}
    normalized = []
    for slot in slots:
        raw = {key: slot[key] for key in ('source', 'tap', 'hold', 'threshold_ms')}
        raw.update({key+'_name': names[raw[key]] for key in ('source', 'tap', 'hold')})
        normalized.append(raw)
    return normalized


def _build(stock, family, settings):
    if sources() != _IMPORTED_SOURCES:
        raise ValueError('Generation sources changed while the app was running. Restart the Development app.')
    if type(stock) is not bytes:
        raise ValueError('Exact stock firmware bytes required.')
    if family == 'rt_only':
        if set(settings) != {'release_raw', 'repress_raw'}:
            raise ValueError('RT recipe fields changed.')
        for value in settings.values():
            if type(value) is not int or not 1 <= value <= 255:
                raise ValueError('RT values must be integers from1 to255.')
        baseline = engine.build(stock, settings['release_raw'], settings['repress_raw'])
        if engine.validate_candidate(stock, baseline) != (settings['release_raw'], settings['repress_raw']):
            raise ValueError('RT baseline audit failed.')
        original_report = {}
    elif family == 'hold':
        if set(settings) != {'slots'}:
            raise ValueError('HOLD recipe fields changed.')
        slots = normalize_hold(settings['slots'])
        settings = {'slots': [{key: s[key] for key in ('source', 'tap', 'hold', 'threshold_ms')} for s in slots]}
        baseline, original_report = hold.build(stock, slots)
    else:
        raise ValueError('Unsupported metadata build family.')
    template_bytes = (HERE/'patch_template.json').read_bytes()
    if digest(template_bytes) != TEMPLATE_SHA:
        raise ValueError('Reviewed metadata template changed.')
    template = json.loads(template_bytes)
    source = sources()
    recipe = {'schema': 1, 'purpose': 'Development_GUI_metadata_generation_v1',
              'channel': 'development', 'product': 1, 'stock': 1, 'family': family,
              'stock_sha256': engine.STOCK_SHA256, 'baseline_sha256': digest(baseline),
              'settings': settings, 'sources': source, 'template_sha256': TEMPLATE_SHA,
              'wire': 'TRID1_index7_nonlocalized_v1_0'}
    entry = entry_for(recipe)
    descriptor = envelope.encode_identity(codec.Identity(1, 1, family, entry['build_id']))
    out = bytearray(baseline)
    allowed = bytearray(len(out)); allowed[:4] = bytes([1])*4
    for section in template['sections']:
        start, end = section['start'], section['end']
        if baseline[start:end] != bytes.fromhex(section['original_hex']):
            raise ValueError('Metadata insertion baseline differs from reviewed bytes.')
        data = descriptor if section['name'] == 'descriptor' else bytes.fromhex(section['data_hex'])
        if len(data) != end-start:
            raise ValueError('Metadata section size changed.')
        out[start:end] = data
        allowed[start:end] = bytes([1])*(end-start)
    image = refresh(out)
    if any(a != b and not allowed[i] for i, (a, b) in enumerate(zip(baseline, image))):
        raise ValueError('Metadata changes escaped the exact section/CRC whitelist.')
    if image[65540:] != baseline[65540:] or sources() != source:
        raise ValueError('Firmware tail or generation sources changed.')
    report = {**original_report, 'schema': 'toprert-development-metadata-build-v1',
              'channel': 'Development', 'family': family, 'identity': entry, 'recipe': recipe,
              'output_sha256': digest(image), 'size': len(image),
              'main_crc': f'0x{int.from_bytes(image[2:4], "little"):04X}',
              'global_crc': f'0x{int.from_bytes(image[:2], "little"):04X}',
              'metadata_span_bytes': 196, 'metadata_static_RAM_bytes': 0,
              'settings_read_back': False, 'hardware_tested': False}
    return image, report


def build_rt(stock, release_raw, repress_raw):
    return _build(stock, 'rt_only', {'release_raw': release_raw, 'repress_raw': repress_raw})


def build_hold(stock, slots):
    return _build(stock, 'hold', {'slots': slots})


def validate(stock, image, report, *, family=None):
    if type(report) is not dict or report.get('schema') != 'toprert-development-metadata-build-v1':
        raise ValueError('Metadata generation manifest required.')
    recipe = report['recipe']
    if family is not None and recipe['family'] != family:
        raise ValueError('Firmware family does not match this installation path.')
    rebuilt, expected = _build(stock, recipe['family'], recipe['settings'])
    if type(image) is not bytes or image != rebuilt or canonical(report) != canonical(expected):
        raise ValueError('Firmware or manifest does not match an exact fresh rebuild.')
    return expected


_IMPORTED_SOURCES = sources()
