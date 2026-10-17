"""Development HOLD metadata validator and the unchanged guarded HOLD transport.

Default is offline. --flash requires the exact GUI-confirmed SHA token.
"""
import argparse
from pathlib import Path
import re
import sys

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP/'backends/hhkb'))
import hhkb_v013_validated_flasher_v0_1 as legacy
from firmware_identity import generation as gen, registry


def parse_hfb(path, expected_sha, stock_path, manifest_path):
    data = Path(path).read_bytes()
    if not re.fullmatch('[0-9a-f]{64}', expected_sha) or gen.digest(data) != expected_sha:
        raise ValueError('Candidate SHA does not match the confirmed file.')
    report = registry.load(manifest_path)
    gen.validate(Path(stock_path).read_bytes(), data, report, family='hold')
    return {'data': data, 'sha': expected_sha, 'global_crc': int.from_bytes(data[:2], 'little'),
            'main_crc': int.from_bytes(data[2:4], 'little'), 'main_crc_bytes': data[2:4],
            'global_crc_bytes': data[:2], 'main': data[4:65540], 'firm_raw': data, 'firm_size': len(data)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hfb', type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--expected-sha', required=True)
    parser.add_argument('--confirm-token', required=True)
    parser.add_argument('--flash', action='store_true')
    args = parser.parse_args()
    expected = args.expected_sha.lower().strip()
    if args.confirm_token != 'FLASH-'+expected[:12].upper():
        raise ValueError('Exact confirmation token required.')
    fw = parse_hfb(args.hfb, expected, args.baseline, args.manifest)
    e1, e2, e3 = legacy.build_packets(fw)
    print('Development metadata candidate: exact rebuild / SHA / CRC PASS.', flush=True)
    if args.flash:
        legacy.do_flash(fw, e1, e2, e3)


if __name__ == '__main__':
    main()
