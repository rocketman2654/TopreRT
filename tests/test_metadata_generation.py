"""Exact firmware generation, registry and dry-run validation. No USB access."""
from contextlib import contextmanager
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch, PropertyMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from firmware_identity import generation as gen, registry, codec, usb_string_codec as envelope
import firmware_inspection as inspection
import firmware_detection as display
import hhkb_metadata_flasher as flasher


class GenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock_path = os.environ.get('TOPRERT_TEST_STOCK')
        if not stock_path:
            raise unittest.SkipTest('Exact stock firmware required: set TOPRERT_TEST_STOCK to a local A0.48 HFB; firmware is not bundled')
        cls.stock = Path(stock_path).read_bytes()
        cls.rt, cls.rt_report = gen.build_rt(cls.stock, 60, 90)
        cls.slots = [gen.hold.parse_slot('SPACE>SPACE>FN:250')]
        cls.hold, cls.hold_report = gen.build_hold(cls.stock, cls.slots)

    @contextmanager
    def scratch(self):
        with tempfile.TemporaryDirectory(dir=gen.APP.parent, prefix='.metadata-generation-') as name:
            yield Path(name)

    def test_default_builds_reproduce_and_keep_reviewed_code_whitelist_and_configuration(self):
        template = json.loads((gen.HERE/'patch_template.json').read_bytes())
        for image, report, baseline in ((self.rt, self.rt_report, gen.engine.build(self.stock, 60, 90)),
                                        (self.hold, self.hold_report, gen.hold.build(self.stock, self.slots)[0])):
            checked = gen.validate(self.stock, image, report)
            self.assertEqual(checked, report)
            self.assertFalse(report['hardware_tested'])
            self.assertFalse(report['settings_read_back'])
            self.assertEqual(report['identity']['channel'], 'development')
            self.assertIsNone(report['identity']['patch_version'])
            allowed = set(range(4))
            for section in template['sections']:
                start, end = section['start'], section['end']; allowed.update(range(start, end))
                if section['name'] == 'descriptor':
                    claim = envelope.parse_descriptor(image[start:end], expected_product=1)
                    self.assertEqual(claim.family, report['family'])
                    self.assertEqual(claim.build_id, report['identity']['build_id'])
                else:
                    self.assertEqual(image[start:end], bytes.fromhex(section['data_hex']))
            self.assertTrue(all(i in allowed for i, (a, b) in enumerate(zip(image, baseline)) if a != b))
            self.assertEqual(image[65540:], baseline[65540:])
            self.assertEqual(gen.crc(image[4:65540]), int.from_bytes(image[2:4], 'little'))
            self.assertEqual(gen.crc(image[2:]), int.from_bytes(image[:2], 'little'))
            self.assertEqual(gen.engine.crc16(image[4:65540]), int.from_bytes(image[2:4], 'little'))
            self.assertEqual(gen.engine.crc16(image[2:]), int.from_bytes(image[:2], 'little'))

    def test_rt_profile_and_hold_threshold_changes_get_new_deterministic_ids(self):
        image, report = gen.build_rt(self.stock, 32, 32)
        self.assertNotEqual(report['identity']['build_id'], self.rt_report['identity']['build_id'])
        self.assertEqual(image[gen.engine.RELEASE_IMM], 32)
        self.assertEqual(image[gen.engine.REPRESS_IMM], 32)
        image2, report2 = gen.build_rt(self.stock, 32, 32)
        self.assertEqual((image, report), (image2, report2))
        with self.scratch() as folder:
            registry.register(report, folder)
            text = envelope.encode_identity(codec.Identity(1, 1, 'rt_only', report['identity']['build_id']))[2:].decode('utf-16-le')
            claim = gen.catalog.resolve_text(text, expected_product=1, catalog_document=gen.catalog.load_catalog(registry.reader_catalog(folder)))
            self.assertEqual(registry.profile_for(claim, folder)['source'], 'local generation recipe')
        _, report3 = gen.build_hold(self.stock, [gen.hold.parse_slot('SPACE>SPACE>FN:180')])
        self.assertNotEqual(report3['identity']['build_id'], self.hold_report['identity']['build_id'])
        self.assertEqual(report3['recipe']['settings']['slots'][0]['threshold_ms'], 180)

    def test_crc_repaired_code_descriptor_alignment_tail_and_profile_mutations_are_rejected(self):
        for offset in (100, 25304, 62016, 62084, 62194, 62196, 65539, 65540, len(self.rt)-1,
                       gen.engine.RELEASE_IMM):
            wrong = bytearray(self.rt); wrong[offset] ^= 1
            wrong = gen.refresh(wrong)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                gen.validate(self.stock, wrong, self.rt_report)

    def test_wrong_family_recipe_manifest_or_source_binding_is_rejected(self):
        for key, value in (('output_sha256', '0'*64), ('channel', 'Release'), ('size', 1)):
            wrong = copy.deepcopy(self.rt_report); wrong[key] = value
            with self.assertRaises(ValueError):gen.validate(self.stock, self.rt, wrong)
        wrong = copy.deepcopy(self.rt_report); wrong['recipe']['settings']['release_raw'] = 61
        with self.assertRaises(ValueError):gen.validate(self.stock, self.rt, wrong)
        with self.assertRaises(ValueError):gen.validate(self.stock, self.rt, self.rt_report, family='hold')
        with patch.object(gen, 'sources', return_value={'changed.py': '0'*64}):
            with self.assertRaises(ValueError):gen.validate(self.stock, self.rt, self.rt_report)

    def test_input_bounds_and_template_mutation_fail_before_any_transport(self):
        for value in (0, 256, True, '60'):
            with self.assertRaises((ValueError, gen.engine.Reject)):gen.build_rt(self.stock, value, 90)
        original = Path.read_bytes
        def read(path):
            data = original(path)
            return data+b' ' if path == gen.HERE/'patch_template.json' else data
        with patch.object(Path, 'read_bytes', read):
            with self.assertRaisesRegex(ValueError, 'template changed|sources changed'):gen.build_rt(self.stock, 60, 90)

    def test_saved_firmware_manifest_and_local_catalog_are_read_back_and_portable(self):
        with self.scratch() as folder:
            root = folder/'identity'; target = folder/'RT.hfb'
            registry.write_build(target, self.rt, self.rt_report, self.stock, root)
            document = gen.catalog.load_catalog(registry.reader_catalog(root))
            text = envelope.encode_identity(codec.Identity(1, 1, 'rt_only', self.rt_report['identity']['build_id']))[2:].decode('utf-16-le')
            claim = gen.catalog.resolve_text(text, expected_product=1, catalog_document=document)
            self.assertTrue(claim['catalog_match'])
            profile = registry.profile_for(claim, root)
            self.assertEqual(profile['settings'], {'release_raw': 60, 'repress_raw': 90})
            self.assertFalse(profile['settings_read_back'])
            registry.write_build(target, self.rt, self.rt_report, self.stock, root)
            shutil.copytree(root, folder/'other_PC')
            self.assertEqual(registry.profile_for(claim, folder/'other_PC'), profile)

    def test_collision_corrupt_record_and_existing_file_are_never_overwritten(self):
        with self.scratch() as folder:
            root = folder/'identity'; registry.register(self.rt_report, root)
            record = root/'builds'/(self.rt_report['identity']['recipe_sha256']+'.json')
            before = record.read_bytes()
            changed = copy.deepcopy(self.rt_report); changed['output_sha256'] = '0'*64
            with self.assertRaisesRegex(ValueError, 'immutable'):registry.register(changed, root)
            self.assertEqual(record.read_bytes(), before)
            changed = copy.deepcopy(self.hold_report)
            changed['identity']['build_id'] = self.rt_report['identity']['build_id']
            original_entry = gen.entry_for
            def collide(recipe):
                return changed['identity'] if recipe['family']=='hold' else original_entry(recipe)
            with patch.object(gen, 'entry_for', side_effect=collide):
                with self.assertRaisesRegex(ValueError, 'collision'):registry.register(changed, root)
            self.assertEqual(record.read_bytes(), before)
            record.write_bytes(b'{"schema":"wrong"}')
            with self.assertRaises(ValueError):registry.reader_catalog(root)

    def test_versioned_catalog_snapshot_checksums_and_missing_registry_do_not_create_files(self):
        with self.scratch() as folder:
            root = folder/'absent'
            self.assertIsNone(registry.reader_catalog(root))
            self.assertFalse(root.exists())
            bundle = folder/'bundle'; shutil.copytree(registry.HERE, bundle, ignore=shutil.ignore_patterns('__pycache__'))
            with patch.object(registry, 'HERE', bundle):
                registry.bundled()
                (bundle/'known_profiles.json').write_bytes(b'{}')
                with self.assertRaisesRegex(ValueError, 'checksum'):registry.bundled()

    def test_hold_dry_run_validator_and_packet_reassembly_accept_only_exact_new_hold(self):
        with self.scratch() as folder:
            stock = folder/'stock.hfb';stock.write_bytes(self.stock)
            target = folder/'hold.hfb';target.write_bytes(self.hold)
            manifest = folder/'hold.json';manifest.write_bytes(gen.canonical(self.hold_report))
            fw = flasher.parse_hfb(target, gen.digest(self.hold), stock, manifest)
            e1, packets, e3 = flasher.legacy.build_packets(fw)
            self.assertEqual(len(packets), 4960)
            self.assertEqual(b''.join(p[7:5+p[4]] for p in packets), self.hold[2:])
            cmd = [sys.executable, '-I', '-B', flasher.__file__, str(target), '--baseline', str(stock),
                   '--manifest', str(manifest), '--expected-sha', gen.digest(self.hold),
                   '--confirm-token', 'FLASH-'+gen.digest(self.hold)[:12].upper()]
            run = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('rebuild / SHA / CRC PASS', run.stdout)
            target.write_bytes(self.rt);manifest.write_bytes(gen.canonical(self.rt_report))
            with self.assertRaisesRegex(ValueError, 'family'):flasher.parse_hfb(target, gen.digest(self.rt), stock, manifest)

    def test_installed_known_rt_profile_is_labeled_as_recipe_not_live_readback(self):
        resolved = {'status':'registered_build_claim','timestamp_utc':'test','worker_cleanup':'reaped',
            'resolution':{'claimed_family':'rt_only','catalog_match':True,'build_id':0xBA90567B,
                          'channel':'development','registered_patch_version':None}}
        with self.scratch() as folder, patch.object(registry, 'DEFAULT_ROOT', folder/'absent'), \
                patch.object(inspection.reader, 'probe_metadata', return_value=resolved):
            result = inspection.inspect_hhkb(Mock())
            text = display.format_details(result)
            self.assertIn('not read back', text)
            self.assertIn('Release R60 (~0.100 mm)', text)
            self.assertIn('Re-press P90 (~0.150 mm)', text)
            self.assertEqual(result.settings_source, 'bundled build recipe')
            resolved['resolution']['catalog_match'] = False
            resolved['status'] = 'unregistered_build_claim'
            self.assertIsNone(inspection.inspect_hhkb(Mock()).build_settings)

    def test_real_gui_generation_callbacks_save_metadata_and_cancel_rt_before_any_write(self):
        from test_gui_identification_development import TkIntegrationTests
        import toprert_unified_gui as gui
        with self.scratch() as folder, TkIntegrationTests().app() as app, \
                patch.object(gui.UnifiedGUI, 'output_dir', new_callable=PropertyMock, return_value=folder), \
                patch.object(gui.messagebox, 'askyesno', return_value=False), \
                patch.object(app, '_hhkb_flash') as write:
            stock = folder/'stock.hfb';stock.write_bytes(self.stock)
            app.platform.set(gui.PLAT_HHKB)
            app.source_path = stock
            app._apply_hhkb()
            paths = list(folder.glob('TopreRT_Development_RT_*.hfb'))
            self.assertEqual(len(paths), 1)
            report = registry.load(Path(str(paths[0])+'.manifest.json'))
            self.assertEqual(report['family'], 'rt_only')
            gen.validate(self.stock, paths[0].read_bytes(), report)
            write.assert_not_called()
            app.hh_slot_baseline_path = stock
            app._hh_slots_load_spacefn()
            app._hh_slots_build()
            self.assertIsNotNone(app.hh_validated_build_path)
            hold_report = registry.load(Path(str(app.hh_validated_build_path)+'.manifest.json'))
            self.assertEqual(hold_report['family'], 'hold')
            self.assertEqual(str(app.hh_slots_flash_btn.cget('state')), 'normal')
            self.assertEqual(len(registry.records(folder/'identity')), 2)
            app.hh_slot_threshold[0].set('180')
            self.assertIsNone(app.hh_validated_build_path)
            self.assertEqual(str(app.hh_slots_flash_btn.cget('state')), 'disabled')

    def test_validated_cli_requires_flash_flag_and_exact_token_before_shared_transport(self):
        with self.scratch() as folder:
            stock=folder/'stock.hfb';stock.write_bytes(self.stock)
            target=folder/'hold.hfb';target.write_bytes(self.hold)
            manifest=folder/'hold.json';manifest.write_bytes(gen.canonical(self.hold_report))
            argv=['hhkb_metadata_flasher.py',str(target),'--baseline',str(stock),'--manifest',str(manifest),
                  '--expected-sha',gen.digest(self.hold),'--confirm-token','FLASH-'+gen.digest(self.hold)[:12].upper()]
            with patch.object(sys,'argv',argv),patch.object(flasher.legacy,'do_flash') as write:
                flasher.main();write.assert_not_called()
            with patch.object(sys,'argv',argv+['--flash']),patch.object(flasher.legacy,'do_flash') as write:
                flasher.main();write.assert_called_once()
            argv[-1]='WRONG'
            with patch.object(sys,'argv',argv+['--flash']),patch.object(flasher.legacy,'do_flash') as write:
                with self.assertRaisesRegex(ValueError,'token'):flasher.main()
                write.assert_not_called()


if __name__ == '__main__':unittest.main()
