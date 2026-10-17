"""Development GUI inspection: one metadata read, conservative legacy fallback."""
from dataclasses import replace
from datetime import datetime, timezone
import firmware_detection as legacy
from firmware_identity import windows_metadata_probe as reader
from firmware_identity import registry


def inspect_hhkb(hhe):
    try:
        path = registry.reader_catalog()
    except (OSError, ValueError, TypeError, KeyError):
        return legacy.ProbeResult('Unknown', 'The local build catalog could not be validated. No device query was sent.',
            identification_status='metadata_unavailable', metadata_status='catalog_unavailable',
            captured_at=datetime.now(timezone.utc).isoformat())
    response = reader.probe_metadata(catalog_path=path) if path is not None else reader.probe_metadata()
    status = response['status']
    captured = response['timestamp_utc']
    if status in ('registered_build_claim', 'unregistered_build_claim'):
        claim = response['resolution']
        family = claim['claimed_family']
        registered = claim['catalog_match']
        identifier = f"{claim['build_id']:08X}"
        channel = claim['channel'] if registered else None
        version = claim['registered_patch_version'] if registered else None
        exact = version or (f"Not assigned — Development build {identifier}" if channel == 'development'
                            else f"Unknown — unregistered build {identifier}")
        try:
            profile = registry.profile_for(claim)
        except (OSError, ValueError, TypeError, KeyError):
            profile = None  # Optional recipe information must not replace a valid device claim.
        settings = profile['settings'] if profile is not None else None
        catalog_version = registry.load(registry.HERE/'catalog_manifest.json')['catalog_version']
        if path is not None:
            catalog_version += ' + local builds'
        if settings and family == 'rt_only':
            settings = {**settings,
                'release_mm_estimated': registry.gen.engine.raw_to_mm(settings['release_raw']),
                'repress_mm_estimated': registry.gen.engine.raw_to_mm(settings['repress_raw'])}
        return legacy.ProbeResult(
            category='Metadata RT-only' if family == 'rt_only' else 'Metadata HOLD',
            detail='Firmware-reported family/build information; settings and full firmware image have not been read back.',
            device='PD-KB800W', exact_version=exact,
            reported_revision='Not queried (see Device diagnostics)',
            evidence='Validated metadata string, payload CRC and ' + ('registered catalog match' if registered else 'unregistered build claim'),
            metadata='Metadata received; this is a firmware claim, not authentication.',
            captured_at=captured, identification_status='metadata_registered' if registered else 'metadata_unregistered',
            firmware_family=family, exact_version_available=bool(version), build_id=identifier,
            build_channel=channel, metadata_status=status, catalog_match=registered,
            build_settings=settings, settings_source=profile['source'] if profile else None,
            catalog_version=catalog_version)
    if status in ('metadata_unavailable', 'platform_unavailable') and response['worker_cleanup'] == 'reaped':
        # Old firmware can STALL index7. The reaped worker no longer owns a handle.
        # Never fall back after malformed metadata, changed connection or timeout.
        result = legacy.inspect_hhkb(hhe)
        return replace(result, metadata='Build metadata unavailable; legacy identification only.', metadata_status=status)
    mismatch = status == 'catalog_identity_mismatch'
    return legacy.ProbeResult('Unknown',
        'Metadata disagrees with the registered build; no legacy fallback was attempted.' if mismatch else
        'Build inspection could not complete. Check the USB connection and close other keyboard tools. No automatic retry.',
        metadata='Metadata query status: ' + status, metadata_status=status, captured_at=captured,
        identification_status='metadata_mismatch' if mismatch else 'metadata_unavailable')
