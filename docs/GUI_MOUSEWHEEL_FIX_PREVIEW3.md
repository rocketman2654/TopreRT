# GUI Preview 3 — mouse-wheel isolation (firmware unchanged)

This is a desktop GUI-only change based on TopreRT v0.3.0-rc2 / GUI Preview 2.

Changes:

- Removed application-global `<MouseWheel>` binding that could scroll the outer content canvas behind a combobox popup.
- Scoped wheel handling to the GUI content canvas and ordinary widgets inside it via a dedicated Tk binding tag. Combobox popup listboxes and the activity log retain their own scrolling.
- Blocked wheel-driven selection changes on **closed** combobox fields (keyboard model, profile, Observer key/mode, and Source/Tap/Hold), so hover-scrolling does not silently change configuration values.
- Blocked wheel handling on the hidden notebook; RT-only vs SpaceFn/HOLD selection is changed by clicking the prominent mode buttons only.
- Added Linux/X11 `Button-4` and `Button-5` handling alongside Windows `MouseWheel`.

No firmware backend, validator, observer protocol, flasher or RT algorithm was changed. Firmware operations have not been tested on hardware for this GUI preview. Users should first verify on Windows without flashing.

## Manual Windows smoke test

1. Open HHKB, then SpaceFn/HOLD mode.
2. Open a Source, Tap or Hold dropdown and scroll its options: the outer window should not move.
3. Close the dropdown, then hover and wheel over a selection box: the selected value should not change.
4. Wheel over a normal label or blank settings area: the settings pane scrolls.
5. Wheel over the activity log: the outer pane stays in place.
6. Wheel over RT-only / SpaceFn buttons: the firmware mode does not switch.
7. Click the buttons to switch: mode and correct apply controls update normally.
8. Confirm HHKB/REALFORCE selection and the bottom action row remain accessible.

_Do not flash firmware while testing UI fixes._
