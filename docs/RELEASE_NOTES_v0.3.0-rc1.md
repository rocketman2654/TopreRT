# TopreRT v0.3.0-rc1

This release candidate promotes the HHKB Generic HOLD / dual-role work from the alpha
test track into a commit-ready integration candidate.

## HHKB changes

- Up to 8 configurable dual-role slots.
- Per-slot Source / Tap / Hold / Threshold.
- Generic descriptor `+3` HOLD action.
- Hardware-tested ordinary HOLD targets.
- Hardware-tested modifier HOLD targets.
- Physical/synthetic ownership arbitration.
- Multi-slot handoff between different Hold actions.
- SHA/diff/CRC-gated GUI build and flashing.

## Hardware-validated HOLD targets

- CTRL
- LALT
- V
- SPACE

## Intentionally blocked

- LSHIFT HOLD
- RSHIFT HOLD
- FN HOLD
- LSHIFT Source/Tap

These remain separate modifier/special-key research items and are not silently exposed.

## Safety

The HHKB GUI custom builder is locked to exact stock A0.48 by SHA-256. It reconstructs
the hardware-tested rev2.2 executable core locally from audited byte substitutions.
After reconstruction, a custom HFB may differ only in the CRC header and 64-byte slot
descriptor table before flashing is enabled. No stock or pre-patched HFB is distributed.

## Known limitation

The current state-machine family still has a documented stock-key autorepeat edge case
when a configured key remains OS-visible while another configured slot owns a Hold
action. This release candidate does not attempt to hide or suppress that behavior with
an unsafe blanket rule.
