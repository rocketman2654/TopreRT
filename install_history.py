"""Bounded, private PC operation history; never device firmware identification.

Call record_event only after the existing operation has succeeded. Supply the
SHA-256 of the exact bytes used by that operation, not a later file reread.
The caller owns the history path (normally in the development app's output).
No firmware files, device identifiers, paths, or free-form notes are retained.
History is local, editable and unauthenticated. A model match does not establish
that the connected keyboard is the keyboard involved in an earlier operation.
"""

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading


SCHEMA_VERSION = 1
DEFAULT_MAX_RECORDS = 20
MAX_RECORDS = 100
MAX_FILE_BYTES = 256 * 1024
_LOCK = threading.RLock()
_R3S_MODELS = {"R3S", "R3SA", "R3SB", "R3SC", "R3SD"}
# Public key labels only; do not retain arbitrary text from slot dictionaries.
_KEY_NAMES = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") | set(
    "ESC MINUS EQUAL BACKSLASH GRAVE TAB LBRACKET RBRACKET BACKSPACE CTRL "
    "SEMICOLON QUOTE ENTER LSHIFT COMMA DOT SLASH RSHIFT FN LALT LGUI SPACE RGUI RALT".split())
_RECORD_FIELDS = {
    "timestamp_utc", "event", "model", "firmware_sha256", "application_build",
    "application_title", "application_channel", "intended_mode", "settings",
    "completion_status", "reconnect_status", "evidence_scope", "match_scope",
    "device_firmware_verified",
}


def _model(value):
    if not isinstance(value, str):
        raise ValueError("Unsupported model")
    value = value.strip().upper()
    if value not in _R3S_MODELS and not re.fullmatch(r"PD-KB8[0-9]{2}[A-Z]{0,3}", value):
        raise ValueError("Unsupported model")
    return value


def _text(value, limit):
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(not c.isprintable() or c in "/\\:" for c in value)):
        raise ValueError("Invalid application description")
    return value.strip()


def _integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Invalid numeric setting")
    return value


def _settings(value, mode):
    if value is None:
        return {}
    if type(value) is not dict:
        raise ValueError("Settings must be a mapping")
    allowed = {"release_raw", "repress_raw", "release_mm", "repress_mm"} if mode == "rt" else (
        {"slots"} if mode == "hold" else set())
    if set(value) - allowed:
        raise ValueError("Unsupported setting (no private/free-form fields allowed)")
    result = {}
    for key, item in value.items():
        if key.endswith("_raw"):
            result[key] = _integer(item, 0, 65535)
        elif key.endswith("_mm"):
            if type(item) not in (int, float) or not math.isfinite(item) or not 0 <= item <= 10:
                raise ValueError("Invalid millimeter setting")
            result[key] = item
        else:
            if type(item) is not list or len(item) > 8:
                raise ValueError("Invalid HOLD slots")
            slots = []
            for slot in item:
                fields = {"source_name", "tap_name", "hold_name", "threshold_ms"}
                if type(slot) is not dict or set(slot) != fields:
                    raise ValueError("Invalid HOLD slot fields")
                clean = {}
                for name in ("source_name", "tap_name", "hold_name"):
                    key_name = slot[name]
                    if not isinstance(key_name, str) or key_name not in _KEY_NAMES:
                        raise ValueError("Invalid key name")
                    clean[name] = key_name
                clean["threshold_ms"] = _integer(slot["threshold_ms"], 1, 65535)
                slots.append(clean)
            result[key] = slots
    return result


def _validated_record(value):
    if type(value) is not dict or set(value) != _RECORD_FIELDS:
        raise ValueError("Invalid record fields")
    stamp = value["timestamp_utc"]
    if not isinstance(stamp, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z", stamp):
        raise ValueError("Invalid UTC timestamp")
    datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S.%fZ")
    model = _model(value["model"])
    event, mode = value["event"], value["intended_mode"]
    if mode not in ("rt", "hold", "stock") or value["completion_status"] != "completed":
        raise ValueError("Only completed supported operations belong in history")
    if event == "installed":
        if model in _R3S_MODELS or value["reconnect_status"] != "verified":
            raise ValueError("Install history requires a completed HHKB reconnect")
    elif event == "generated":
        if model not in _R3S_MODELS or mode != "rt" or value["reconnect_status"] != "not_applicable":
            raise ValueError("Generation history is only an R3S RT file operation")
    else:
        raise ValueError("Unsupported operation")
    sha = value["firmware_sha256"]
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", sha):
        raise ValueError("Invalid firmware SHA-256")
    if value["application_channel"] not in ("development", "release"):
        raise ValueError("Unsupported application channel")
    if (value["evidence_scope"] != "pc_operation_history"
            or value["match_scope"] != "model_only"
            or value["device_firmware_verified"] is not False):
        raise ValueError("History must not claim device firmware identification")
    clean = dict(value)
    clean.update(model=model, firmware_sha256=sha.lower(),
                 application_build=_text(value["application_build"], 96),
                 application_title=_text(value["application_title"], 160),
                 settings=_settings(value["settings"], mode))
    return clean


def _limit(value):
    return _integer(value, 1, MAX_RECORDS)


def load_history(path, *, max_records=DEFAULT_MAX_RECORDS):
    """Return validated records newest first; missing/malformed history is empty.

    Invalid individual entries are discarded. Unknown schemas, oversized files,
    and invalid envelopes are ignored entirely. Returned data is a fresh copy.
    """
    try:
        limit = _limit(max_records)
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            return []
        data = json.loads(raw.decode("utf-8"))
        if (type(data) is not dict or set(data) != {"schema_version", "records"}
                or type(data["schema_version"]) is not int
                or data["schema_version"] != SCHEMA_VERSION
                or type(data["records"]) is not list or len(data["records"]) > MAX_RECORDS):
            return []
        records = []
        for entry in data["records"]:
            try:
                records.append(_validated_record(entry))
            except (ValueError, TypeError, OverflowError):
                continue
            if len(records) == limit:
                break
        return records
    except Exception:
        return []


def record_event(path, *, event, model, firmware_sha256, application_build,
                 application_title, application_channel, intended_mode,
                 settings=None, completion_status="completed", reconnect_status,
                 max_records=DEFAULT_MAX_RECORDS):
    """Best effort atomic append, returning False on validation or write failure.

    This function must never turn a successful firmware operation into a failure
    or a reason to retry flashing. It performs no device access. Only completed
    HHKB installs with verified reconnect or completed R3S file generation are
    accepted. 'Verified reconnect' is the caller's updater result, not firmware
    readback. Settings describe intent, not values read from the keyboard.
    Calls in this process are serialized; simultaneous separate app processes
    can replace each other's newest history entry.
    """
    temporary = None
    try:
        limit = _limit(max_records)
        record = _validated_record({
            "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "event": event, "model": model, "firmware_sha256": firmware_sha256,
            "application_build": application_build, "application_title": application_title,
            "application_channel": application_channel, "intended_mode": intended_mode,
            "settings": settings, "completion_status": completion_status,
            "reconnect_status": reconnect_status, "evidence_scope": "pc_operation_history",
            "match_scope": "model_only", "device_firmware_verified": False,
        })
        target = Path(path)
        with _LOCK:
            records = [record] + load_history(target, max_records=limit)[:limit - 1]
            encoded = json.dumps({"schema_version": SCHEMA_VERSION, "records": records},
                                 indent=2, ensure_ascii=False, allow_nan=False).encode("utf-8")
            if len(encoded) > MAX_FILE_BYTES:
                return False
            target.parent.mkdir(parents=True, exist_ok=True)
            # A temporary sibling allows atomic replacement on the same volume.
            with tempfile.NamedTemporaryFile(mode="wb", dir=target.parent,
                                             prefix=".install-history-", suffix=".tmp",
                                             delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            temporary = None
        return True
    except Exception:
        return False
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def latest_record_for_model(path, model, *, event=None):
    """Latest PC record matching this model only, never a device identity match.

    An optional event filter keeps file generation separate from installation.
    Returns None when unavailable or unsupported. Local history can be stale.
    """
    try:
        model = _model(model)
        if event not in (None, "installed", "generated"):
            return None
        return next((entry for entry in load_history(path, max_records=MAX_RECORDS)
                     if entry["model"] == model and (event is None or entry["event"] == event)), None)
    except Exception:
        return None
