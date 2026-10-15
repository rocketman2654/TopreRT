# GUI Preview 2 — high contrast firmware mode selector

This updates **the GUI only**, based on GUI Preview 1 (RC2 backend unchanged).

- Replace difficult-to-see Windows native Notebook tabs with large, high-contrast selection buttons labelled RAPID TRIGGER (RT-only) and SPACEFN / GENERIC HOLD.
- The active selection turns dark green. The inactive selection stays light gray.
- Retain distinct RT-only apply and HOLD Build & Validate / Flash actions. Nothing is combined on the firmware side.
- Hide the selector when REALFORCE R3S is selected (RT-only).
- Preserve the scrollable content and fixed action footer from Preview 1.

Safety: **No device has been flashed** by the testing process. Linux virtual-display GUI tests do not substitute for a Windows hardware test.

Test: unpack outside the Git working tree, run `Start_TopreRT_GUI.bat`, choose HHKB, click both large mode buttons. Verify active color and correct footer actions. Do not flash to test the layout.
