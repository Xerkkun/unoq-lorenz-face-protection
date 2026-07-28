# STM32U585 forwarded-status sketch

This sketch is an observability endpoint for the Linux application, not the
ROI protection implementation and not an independent latency instrument.

The Router Bridge callback is:

```text
record_metrics(frameId, linuxProtectUs, roiCount, authenticatedMode)
```

- `linuxProtectUs` is calculated and forwarded by Linux. The MCU does not
  measure that interval.
- `authenticatedMode` states which experimental mode Linux reported; it is not
  proof that a particular packet was persisted or accepted by a receiver.
- The built-in LED is on for a reported authenticated mode and off for an
  unauthenticated ablation. It is a mode indicator, not a tamper alarm.

The sketch keeps a 32-message circular buffer, counts authenticated,
unauthenticated, invalid, and overwritten messages, and prints a
`forwarded_metrics_status` JSON object at 115200 baud once per second. The
serial field is deliberately named `last_linux_reported_protect_us` to prevent
it from being reported as an STM32 timing result.

For the paper, derive board-pipeline timing from the versioned Linux CSV. Use
the serial output only to audit bridge delivery and visible mode state. A true
MCU timing experiment would require a separate protocol, an explicitly placed
hardware timer, and calibration of the measurement boundary.
