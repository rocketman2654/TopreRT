# RT / HOLD progress display — Development

RT installation, stock restoration and HOLD installation now share the same two-line transfer display:

```text
Writing 50.0% · Packets 2,480 / 4,960
Elapsed 00:30 · Transfer ETA 00:31 · 80.0 pkt/s
```

The actual values come from acknowledged packet counts. Rate/ETA start as measuring/estimating until sufficient elapsed time is available. The ETA covers the remaining packet transfer, not finalization or reconnect. It is an estimate, not a guarantee. A transfer at 100% is not complete device verification.

Both writers reserve the final part of the overall bar for finalization/reconnection. The footer now puts a full-width bar above the same wrapped metrics instead of truncating detail into a narrow right-side label. Update command/ACK handling and identity checks are unchanged.

This is post-rc3 development UI work only. It is excluded from the isolated HOLD query correction candidate and PR #4. The currently running candidate is not modified. No hardware commands were sent to verify this display.

Validation: representative startup and measured-rate strings and real Tk widget creation with discovery mocked passed. The existing 71-test offline app suite passed on rerun. An initial run hit the previously recorded intermittent mocked identity-probe report failure. These results are separate from hardware evidence.
