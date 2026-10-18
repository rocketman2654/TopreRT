"""Immutable artifact publication races; no stock firmware or USB required."""
import os
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from firmware_identity import registry
import firmware_inspection as inspection


class RegistryPublicationTests(unittest.TestCase):
    def scratch(self):
        return tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2])

    def publisher(self):
        return 'rename' if os.name == 'nt' else 'link'

    def test_competing_writer_cannot_be_overwritten(self):
        with self.scratch() as folder:
            target = Path(folder) / 'artifact.json'
            operation = self.publisher()
            original = getattr(registry.os, operation)

            def publish_after_competitor(source, destination):
                Path(destination).write_bytes(b'other writer')
                return original(source, destination)

            with patch.object(registry.os, operation, side_effect=publish_after_competitor), \
                    self.assertRaisesRegex(ValueError, 'Concurrent'):
                registry.save_once(target, b'this writer')
            self.assertEqual(target.read_bytes(), b'other writer')
            self.assertEqual(list(Path(folder).iterdir()), [target])

    def test_identical_concurrent_publication_is_idempotent(self):
        with self.scratch() as folder:
            target = Path(folder) / 'artifact.json'
            operation = self.publisher()
            original = getattr(registry.os, operation)

            def publish_after_same_writer(source, destination):
                Path(destination).write_bytes(b'same bytes')
                return original(source, destination)

            with patch.object(registry.os, operation, side_effect=publish_after_same_writer):
                registry.save_once(target, b'same bytes')
            self.assertEqual(target.read_bytes(), b'same bytes')
            self.assertEqual(list(Path(folder).iterdir()), [target])

    def test_existing_file_and_new_publication_keep_exact_bytes(self):
        with self.scratch() as folder:
            target = Path(folder) / 'artifact.json'
            registry.save_once(target, b'original')
            registry.save_once(target, b'original')
            with self.assertRaisesRegex(ValueError, 'immutable'):
                registry.save_once(target, b'different')
            self.assertEqual(target.read_bytes(), b'original')

    def test_publication_failure_leaves_no_partial_file_or_temporary(self):
        with self.scratch() as folder:
            target = Path(folder) / 'artifact.json'
            with patch.object(registry.os, self.publisher(), side_effect=PermissionError), \
                    self.assertRaises(PermissionError):
                registry.save_once(target, b'not published')
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_real_simultaneous_writers_preserve_one_complete_winner(self):
        with self.scratch() as folder:
            target = Path(folder) / 'artifact.json'
            barrier = threading.Barrier(2, timeout=5)
            operation = self.publisher()
            original = getattr(registry.os, operation)

            def synchronized_publish(source, destination):
                barrier.wait()
                return original(source, destination)

            def write(data):
                try:
                    registry.save_once(target, data)
                    return 'saved'
                except ValueError:
                    return 'conflict'

            with patch.object(registry.os, operation, side_effect=synchronized_publish), \
                    ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(write, data) for data in (b'A' * 4096, b'B' * 4096)]
                results = [future.result(timeout=10) for future in futures]
            self.assertEqual(sorted(results), ['conflict', 'saved'])
            self.assertIn(target.read_bytes(), (b'A' * 4096, b'B' * 4096))
            self.assertEqual(list(Path(folder).iterdir()), [target])


class RegistryRecordValidationTests(unittest.TestCase):
    def test_non_object_records_stop_inspection_before_any_device_query(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as folder:
            root = Path(folder) / 'identity'
            (root / 'builds').mkdir(parents=True)
            for value in (None, [], 'unexpected text', 5, True):
                with self.subTest(value=value):
                    (root / 'builds' / 'broken.json').write_text(json.dumps(value), encoding='utf-8')
                    with patch.object(registry, 'DEFAULT_ROOT', root), \
                            patch.object(inspection.reader, 'probe_metadata') as query, \
                            patch.object(inspection.legacy, 'inspect_hhkb') as legacy:
                        result = inspection.inspect_hhkb(Mock())
                    self.assertEqual(result.metadata_status, 'catalog_unavailable')
                    query.assert_not_called()
                    legacy.assert_not_called()


if __name__ == '__main__':
    unittest.main()
