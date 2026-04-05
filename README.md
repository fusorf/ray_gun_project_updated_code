# Ray Gun Mark I - Updated Code

Updated CircuitPython code for the Ray Gun Mark I prop replica, running on an **Adafruit RP2040 Prop-Maker Feather**.

Based on the original code by Andrew Lamson (11/28/2023).

## Changes from original code

### 1. Hall Effect Sensor: Digital latched -> Analog non-latched (49E)

**Original:** Digital input on `D6` with pull-up, using a latched hall sensor. Required a workaround that periodically power-cycled `EXTERNAL_POWER` every ~1s to reset the latch, which caused NeoPixel glitches and required a consecutive-read confirmation filter (`HALL_CONFIRM_READS = 3`).

**Updated:** Analog input on `A0` using a 49E linear hall sensor (non-latched). The sensor outputs a voltage proportional to magnetic field strength:
- Barrel closed (magnet near): ~64000-65500
- Barrel open (magnet far): ~46400-47000

Uses two thresholds with hysteresis to prevent flickering, **auto-calibrated at boot**:
- Reads the hall sensor baseline with barrel closed at startup
- Sets `HALL_OPEN_THRESHOLD = baseline - 12000` and `HALL_CLOSED_THRESHOLD = baseline - 9000`
- This handles voltage differences between USB power (~64000 baseline) and LiPo battery (~49000 baseline)
- **Important: barrel must be closed at power-on for correct calibration**

Additionally, a 500ms fire lockout prevents servo vibration from triggering false barrel-open detections.

**Removed:**
- `EXTERNAL_POWER` power-cycle reset hack
- Consecutive-read confirmation (`hall_open_count`, `HALL_CONFIRM_READS`)
- Variables: `loop_count`, `HALL_RESET_INTERVAL`

### 2. Hall sensor debounce

**Original:** No debounce - barrel state changed on any single-frame sensor transition (`hallstate != last_hallstate`), making it susceptible to glitches.

**Updated:** 100ms debounce (`HALL_DEBOUNCE = 0.1`) on hall state changes prevents rapid false triggers.

### 3. Trigger: barrel-open guard

**Original:** Trigger condition checked `not sensor.value` directly in the loop, reading the raw sensor instead of using the barrel state. This meant the trigger relied on the hall sensor reading being stable at that exact moment.

**Updated:** Trigger condition uses `not barrel_open` (the debounced state variable), making firing immune to hall sensor noise.

### 4. Servo auto-return timer

**Original:** Servo moved to `needle_yellow` on fire and returned to `needle_green` only on trigger release. If the trigger was held or released too quickly, the servo behavior was inconsistent.

**Updated:** Added `servo_fire_time` and `SERVO_MIN_DURATION = 0.35s` - the servo stays at yellow for at least 350ms before auto-returning to green, regardless of trigger timing. This ensures a visible needle deflection on every shot.

### 5. Photocell threshold recalibration

**Original:** Battery detection threshold was `photostate < 500` / `photostate > 500`.

**Updated:** Threshold changed to `photostate < 200` based on measured values with the cell LED:
- Battery present (obstructed): ~56-76
- Battery absent (light path clear): ~1000

### 6. Battery sound detection: edge-count -> sequence-based

**Original:** Simple edge detection with `last_bat != bat` and a counter `b` that only allowed one `batteryOut` sound. The logic was fragile and could not reliably distinguish insertion from removal with two batteries in series.

**Updated:** Sequence-based detection using a 6-step state machine that matches the physical sequence of two batteries passing through the photocell:

| Step | Photocell state | Sound | Event |
|------|----------------|-------|-------|
| 1 | -> HIGH (clear) | batteryOut | 1st battery leaves |
| 2 | -> LOW (blocked) | *(silent)* | 2nd battery passing |
| 3 | -> HIGH (clear) | batteryOut | 2nd battery leaves |
| 4 | -> LOW (blocked) | batteryIn | 1st battery inserted |
| 5 | -> HIGH (clear) | *(silent)* | Gap between batteries |
| 6 | -> LOW (blocked) | batteryIn | 2nd battery seated |
| 7+ | any | *(silent)* | Sequence complete |

The sequence counter resets when the barrel opens or closes.

### 7. Debug logging

**Original:** No serial output.

**Updated:** Serial print statements for debugging:
- `[STARTUP]` - hall sensor value at boot
- `[FIRE]` - shot count and servo angle
- `[BARREL OPEN/CLOSE]` - hall raw value at transition
- `[PHOTO]` - periodic photocell value (fast when barrel open, slow otherwise)
- `[BAT EDGE]` - photocell state changes
- `[BAT IN/OUT/SILENT]` - battery sequence events

## Pin mapping

| Pin | Function |
|-----|----------|
| A0 | Hall Effect Sensor (49E analog) |
| A1 | Potentiometer |
| A2 | Photocell |
| D4 | Servo motor (PWM) |
| D5 | Trigger (digital input) |
| D9 | Dial NeoPixels (PWM) |
| D10 | Cell reference LED (NeoPixel) |
| EXTERNAL_NEOPIXELS | Fuse NeoPixels |
| EXTERNAL_BUTTON | Power switch |

## Hardware

- Adafruit RP2040 Prop-Maker Feather
- 49E linear Hall effect sensor (non-latched, analog)
- Photocell + white reference LED for battery detection
- SG90 micro servo for gauge needle
- NeoPixel strips (fuse + dial + cell)
- I2S speaker output
