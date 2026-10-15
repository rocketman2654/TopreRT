import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import firmware_detection as fd


def response(prefix, size):
    return prefix.ljust(size, b"\0")


class IdentificationTests(unittest.TestCase):
    def test_no_response_or_truncated_signature_is_not_stock(self):
        for payload in (b"", b"random", fd.RT_OBSERVER_PREFIX):
            result = fd.classify_responses(payload, None)
            self.assertEqual(result.category, "Unknown")
            self.assertIn("Unknown", result.exact_version)

    def test_rt_response_does_not_claim_rt_only_or_exact_version(self):
        rt = response(fd.RT_OBSERVER_PREFIX, 16)
        result = fd.classify_responses(rt, rt)
        self.assertEqual(result.category, "Legacy TopreRT")
        self.assertIn("Unknown", result.exact_version)
        self.assertIn("does not prove RT-only", result.detail)

    def test_hold_family_does_not_claim_release_or_spacefn(self):
        result = fd.classify_responses(response(fd.RT_OBSERVER_PREFIX, 16),
                                       response(fd.HOLD_CANARY_PREFIX, 26))
        self.assertEqual(result.category, "Legacy Dual-Role / HOLD")
        self.assertIn("Unknown", result.exact_version)
        self.assertIn("configuration are unknown", result.detail)
        truncated = fd.classify_responses(response(fd.RT_OBSERVER_PREFIX, 16), fd.HOLD_CANARY_PREFIX)
        self.assertEqual(truncated.category, "Legacy TopreRT")

    def fake_engine(self):
        hhe = Mock()
        hhe.enum_vendor.return_value = [{"path": "PRIVATE-PATH"}]
        info = b"PD-KB800W".ljust(20, b"\0") + b"A3\0\0" + b"PRIVATE-SERIAL".ljust(16, b"\0")
        hhe.identity.return_value = (info, b"dips", b"mode")
        hhe.query.side_effect = [info, b"dips", b"mode"]
        hhe.decode_identity.return_value = "PD-KB800W"
        hhe.packet.side_effect = lambda command, body=b"": bytes([command]) + body
        return hhe

    def test_probe_uses_only_legacy_queries_and_exports_no_serial(self):
        hhe = self.fake_engine()
        hhe.rx.side_effect = [response(fd.RT_OBSERVER_PREFIX, 16), response(fd.HOLD_CANARY_PREFIX, 26)]
        result = fd.inspect_hhkb(hhe)
        self.assertEqual([call.args for call in hhe.packet.call_args_list], [(0x99,), (0x99, b"\xc1\xa1")])
        self.assertEqual(result.reported_revision, "A3")
        self.assertIn("Unknown", result.exact_version)
        report = fd.shared_report(result)
        self.assertNotIn("PRIVATE", report)
        self.assertFalse(json.loads(report)["serials_included"])
        self.assertIn("Not queried", result.metadata)
        self.assertTrue(result.captured_at)
        hhe.open_dev.return_value.close.assert_called_once()

    def test_timeout_never_claims_stock_and_skips_specific_query(self):
        hhe = self.fake_engine()
        hhe.rx.side_effect = TimeoutError("private data")
        result = fd.inspect_hhkb(hhe)
        self.assertEqual(result.category, "Unknown")
        self.assertEqual(hhe.tx.call_count, 1)
        self.assertNotIn("private data", fd.shared_report(result))

    def test_unstable_identity_sends_no_telemetry(self):
        hhe = self.fake_engine()
        hhe.query.side_effect = [b"different", b"dips", b"mode"]
        result = fd.inspect_hhkb(hhe)
        self.assertEqual(result.category, "Unknown")
        hhe.tx.assert_not_called()

    def test_labels_distinguish_reported_revision_and_patch_version(self):
        text = fd.format_details(fd.ProbeResult("Legacy TopreRT", "test", reported_revision="A3"))
        self.assertIn("A3 (not the TopreRT version)", text)
        self.assertIn("Exact TopreRT version: Unknown", text)
        self.assertIn("Metadata v1: Not queried", text)
