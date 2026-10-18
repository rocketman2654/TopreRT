import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import firmware_detection as fd


def response(prefix, size):
    if prefix == fd.HOLD_CANARY_PREFIX and size >= 26:
        return (prefix + b"\x52").ljust(size, b"\0")
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
        self.assertEqual(result.identification_status, "legacy_common")
        self.assertEqual(result.firmware_family, "toprert_unspecified")
        self.assertFalse(result.rt_only_verified)
        self.assertIn("RT/HOLD not distinguished", fd.display_title(result))

    def test_hold_family_does_not_claim_release_or_spacefn(self):
        result = fd.classify_responses(response(fd.RT_OBSERVER_PREFIX, 16),
                                       response(fd.HOLD_CANARY_PREFIX, 26))
        self.assertEqual(result.category, "Legacy Dual-Role / HOLD")
        self.assertIn("Unknown", result.exact_version)
        self.assertIn("configuration are unknown", result.detail)
        self.assertEqual(result.identification_status, "legacy_hold")
        self.assertEqual(result.firmware_family, "hold")
        self.assertEqual(result.hold_probe_status, "signature_observed")
        self.assertFalse(result.exact_version_available)
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
        self.assertEqual([call.args for call in hhe.packet.call_args_list], [(0x99,), (0x99, b"\xc1\x52")])
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

    def test_snapshot_timeout_does_not_fall_back_to_canary_initialization(self):
        hhe = self.fake_engine()
        hhe.rx.side_effect = [response(fd.RT_OBSERVER_PREFIX, 16), TimeoutError("unavailable")]
        result = fd.inspect_hhkb(hhe)
        self.assertEqual(result.identification_status, "legacy_common")
        self.assertEqual([call.args for call in hhe.packet.call_args_list], [(0x99,), (0x99, b"\xc1\x52")])

    def test_live_snapshot_rejects_a_stale_initialization_reply(self):
        hhe = self.fake_engine()
        stale = (fd.HOLD_CANARY_PREFIX+b"\xA1").ljust(26, b"\0")
        hhe.rx.side_effect = [response(fd.RT_OBSERVER_PREFIX, 16), stale]
        result = fd.inspect_hhkb(hhe)
        self.assertEqual(result.identification_status, "legacy_common")
        self.assertFalse(result.rt_only_verified)

    def test_unknown_hold_operation_is_not_accepted_as_hold_evidence(self):
        specific = (fd.HOLD_CANARY_PREFIX+b"\xFF").ljust(26, b"\0")
        result = fd.classify_responses(response(fd.RT_OBSERVER_PREFIX, 16), specific)
        self.assertEqual(result.identification_status, "legacy_common")

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
        self.assertNotIn("Metadata v1:", text)
        self.assertIn("Not queried", json.loads(fd.shared_report(fd.ProbeResult("Unknown", "test")))["metadata"])

    def test_absent_invalid_or_truncated_hold_reply_never_proves_rt_only(self):
        for specific in (None, b"", b"random", fd.HOLD_CANARY_PREFIX,
                         response(fd.HOLD_CANARY_PREFIX, 65), response(fd.RT_OBSERVER_PREFIX, 64)):
            with self.subTest(specific=specific):
                result = fd.classify_responses(response(fd.RT_OBSERVER_PREFIX, 64), specific)
                self.assertEqual(result.identification_status, "legacy_common")
                self.assertFalse(result.rt_only_verified)
                self.assertFalse(result.stock_verified)

    def test_hold_signature_without_valid_common_reply_is_not_accepted(self):
        for plain in (b"", fd.RT_OBSERVER_PREFIX, response(fd.RT_OBSERVER_PREFIX, 65)):
            result = fd.classify_responses(plain, response(fd.HOLD_CANARY_PREFIX, 64))
            self.assertEqual(result.firmware_family, "unknown")
            self.assertEqual(result.hold_probe_status, "not_attempted")

    def test_hold_query_failure_retains_common_evidence_and_closes_device(self):
        for phase in ("tx", "rx"):
            hhe = self.fake_engine()
            hhe.rx.side_effect = [response(fd.RT_OBSERVER_PREFIX, 16), RuntimeError("PRIVATE-SERIAL")]
            if phase == "tx":
                hhe.tx.side_effect = [None, RuntimeError("PRIVATE-PATH")]
            result = fd.inspect_hhkb(hhe)
            self.assertEqual(result.identification_status, "legacy_common")
            self.assertEqual(result.hold_probe_status, "query_unavailable")
            self.assertFalse(result.rt_only_verified)
            self.assertNotIn("PRIVATE", fd.shared_report(result))
            hhe.open_dev.return_value.close.assert_called_once()

    def test_connection_errors_are_not_stock_and_omit_exception_data(self):
        for method in ("load_hid", "enum_vendor", "open_dev"):
            hhe = self.fake_engine()
            getattr(hhe, method).side_effect = RuntimeError("PRIVATE-PATH")
            result = fd.inspect_hhkb(hhe)
            self.assertEqual(result.identification_status, "connection_unavailable")
            self.assertFalse(result.stock_verified)
            self.assertNotIn("PRIVATE", fd.shared_report(result))
            hhe.tx.assert_not_called()

    def test_identity_error_sends_no_telemetry(self):
        hhe = self.fake_engine()
        hhe.identity.side_effect = RuntimeError("PRIVATE-SERIAL")
        result = fd.inspect_hhkb(hhe)
        self.assertEqual(result.identification_status, "query_failed")
        self.assertNotIn("PRIVATE", fd.shared_report(result))
        hhe.tx.assert_not_called()
        hhe.open_dev.return_value.close.assert_called_once()

    def test_close_failure_is_sanitized_and_not_a_success(self):
        hhe = self.fake_engine()
        hhe.rx.side_effect = [response(fd.RT_OBSERVER_PREFIX, 16), response(fd.HOLD_CANARY_PREFIX, 26)]
        hhe.open_dev.return_value.close.side_effect = RuntimeError("PRIVATE-PATH")
        with self.assertRaisesRegex(RuntimeError, "Could not close") as caught:
            fd.inspect_hhkb(hhe)
        self.assertNotIn("PRIVATE", str(caught.exception))

    def test_report_states_do_not_claim_legacy_version_or_stock(self):
        for plain, specific in ((b"", None), (response(fd.RT_OBSERVER_PREFIX, 16), None),
                                 (response(fd.RT_OBSERVER_PREFIX, 16), response(fd.HOLD_CANARY_PREFIX, 26))):
            report = json.loads(fd.shared_report(fd.classify_responses(plain, specific)))
            self.assertEqual(report["schema"], "toprert-firmware-identification-v1")
            self.assertFalse(report["stock_verified"])
            self.assertFalse(report["rt_only_verified"])
            self.assertFalse(report["exact_version_available"])
