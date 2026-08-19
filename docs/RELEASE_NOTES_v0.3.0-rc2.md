# TopreRT v0.3.0-rc2 candidate

## Fixes

- Fixes the HHKB Generic HOLD GUI bug where **Build & Validate** could succeed
  but **Flash validated build** remained disabled.
- Root cause: post-write validation called the non-existent
  `validate_baseline()` function instead of `validate_stock()`.

## HHKB SpaceFn

Adds a hardware-verified special case:

- Source: `SPACE`
- Tap: `SPACE`
- Hold: `FN`
- Threshold: user-configurable

Hardware validation completed for the 250 ms test profile:

- tap Space -> Space
- hold Space -> native HHKB Fn layer
- synthetic Fn + physical Fn overlap
- both Fn press/release orders
- rapid reactivation
- repeated threshold-edge use
- multiple Fn-layer functions
- reversed Space / layer-key release order
- no stuck Fn observed

### Scope

`FN` is **not** promoted to an unrestricted generic HOLD target.

The builder accepts `FN` only when:
- Source = `SPACE`
- Tap = `SPACE`
- Hold = `FN`

Other Source -> Fn combinations remain unsupported.

## Safety

- Exact stock HHKB A0.48 input remains SHA-locked.
- Generic HOLD core patch remains unchanged.
- LSHIFT and RSHIFT remain blocked HOLD targets.
- Post-build disk SHA, rebuild equivalence, CRC, and validated-flasher preflight remain in place.
