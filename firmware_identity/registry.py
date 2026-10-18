"""Versioned bundled catalogs plus separate, portable custom build records."""
import json
import os
from pathlib import Path
import tempfile

from . import generation as gen, identity_catalog as catalog

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parent/'output/identity'


def load(path):
    if Path(path).stat().st_size > 1024*1024:
        raise ValueError('Build record exceeds the supported size.')
    return json.loads(Path(path).read_bytes(), object_pairs_hook=catalog._unique_object)


def bundled():
    manifest = load(HERE/'catalog_manifest.json')
    version = manifest['catalog_version']
    if not isinstance(version, str) or not version or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._' for c in version):
        raise ValueError('Invalid catalog version.')
    folder = HERE/'catalogs'/version
    if (folder/'manifest.json').read_bytes() != (HERE/'catalog_manifest.json').read_bytes():
        raise ValueError('Versioned catalog manifest changed.')
    for name in ('build_catalog.json', 'known_profiles.json'):
        data = (HERE/name).read_bytes()
        if gen.digest(data) != manifest['files_sha256'][name] or data != (folder/name).read_bytes():
            raise ValueError('Bundled catalog/profile checksum mismatch.')
    return catalog.load_catalog(HERE/'build_catalog.json')


def _publish_once(temporary, target):
    # Windows rename fails if the target exists; POSIX rename would replace it.
    # Hard-link publication has exclusive-create semantics on POSIX instead.
    if os.name == 'nt':
        os.rename(temporary, target)
    else:
        os.link(temporary, target)


def save_once(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError('An existing immutable build record differs.')
        return
    fd, name = tempfile.mkstemp(prefix='.identity-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data); out.flush(); os.fsync(out.fileno())
        try:
            _publish_once(name, path)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ValueError('Concurrent build record conflict.')
        if path.read_bytes() != data:
            raise ValueError('Build record readback failed.')
    finally:
        if Path(name).exists():
            Path(name).unlink()


def records(root=None):
    folder = Path(root or DEFAULT_ROOT)/'builds'
    if not folder.exists():
        return []
    rows = []
    for path in sorted(folder.glob('*.json')):
        item = load(path)
        if (type(item) is not dict
                or item.get('schema') != 'toprert-development-metadata-build-v1'
                or item.get('identity') != gen.entry_for(item['recipe'])
                or path.stem != item['identity']['recipe_sha256']):
            raise ValueError('Custom build record has inconsistent provenance.')
        rows.append(item)
    return rows


def combined(root=None):
    document = bundled()
    by_id = {entry['build_id']: entry for entry in document['entries']}
    for item in records(root):
        entry = item['identity']; identifier = entry['build_id']
        if identifier in by_id and by_id[identifier] != entry:
            raise ValueError('Build ID collision with a different recipe; no record was replaced.')
        by_id[identifier] = entry
    result = {'schema': 1, 'entries': list(by_id.values())}
    catalog.validate_catalog(result)
    return result


def reader_catalog(root=None):
    root = Path(root or DEFAULT_ROOT)
    bundled()
    if not (root/'builds').exists():
        return None  # No files/directories are created by a first inspection.
    data = gen.canonical(combined(root))
    path = root/'catalogs'/(gen.digest(data)+'.json')
    save_once(path, data)
    return path


def register(report, root=None):
    root = Path(root or DEFAULT_ROOT)
    entry = report['identity']
    if entry != gen.entry_for(report['recipe']):
        raise ValueError('Build entry does not match its generation recipe.')
    existing = combined(root)
    found = next((e for e in existing['entries'] if e['build_id'] == entry['build_id']), None)
    if found is not None and found != entry:
        raise ValueError('Build ID collision; the previous catalog is preserved.')
    path = root/'builds'/(entry['recipe_sha256']+'.json')
    save_once(path, gen.canonical(report))
    catalog_path = reader_catalog(root)
    merged = catalog.load_catalog(catalog_path)
    if entry not in merged['entries']:
        raise ValueError('Registered build not found in catalog readback.')
    return path


def write_build(path, image, report, stock, root=None):
    gen.validate(stock, image, report)
    path = Path(path)
    save_once(path, image)
    save_once(Path(str(path)+'.manifest.json'), gen.canonical(report))
    gen.validate(stock, path.read_bytes(), load(Path(str(path)+'.manifest.json')))
    register(report, root)


def profile_for(claim, root=None):
    if not claim['catalog_match']:
        return None
    document = bundled()
    known = load(HERE/'known_profiles.json')
    for row in known['entries']:
        if (row['build_id'] == claim['build_id'] and row['family'] == claim['claimed_family']
                and any(e['build_id'] == row['build_id'] and e['recipe_sha256'] == row['recipe_sha256']
                        for e in document['entries'])):
            return {'settings': row['settings'], 'source': 'bundled build recipe', 'settings_read_back': False}
    for row in records(root):
        entry = row['identity']
        if (entry['build_id'] == claim['build_id'] and entry['family'] == claim['claimed_family']
                and claim['channel'] == entry['channel']):
            return {'settings': row['recipe']['settings'], 'source': 'local generation recipe', 'settings_read_back': False}
    return None
