# The Ray Gun Project - Ray Gun Mark I
# Code written by Andrew Lamson 11/28/23
# Edited by Val 2025 (final baseline)
# Updated 2026: analog non-latched hall sensor (49E) on A0

import time
import board
import audiocore
import audiobusio
import pwmio
from digitalio import DigitalInOut, Direction, Pull
import analogio
from analogio import AnalogIn
import neopixel
from adafruit_led_animation.animation.SparklePulse import SparklePulse
from adafruit_led_animation.color import BLUE, WHITE, CYAN, GREEN, RED
from adafruit_motor import servo
import adafruit_lis3dh

# Enable external power pin
external_power = DigitalInOut(board.EXTERNAL_POWER)
external_power.direction = Direction.OUTPUT
external_power.value = True

led = DigitalInOut(board.LED)
led.direction = Direction.OUTPUT
led.value = True

# Set up trigger pin
trigger = DigitalInOut(board.D5)
trigger.direction = Direction.INPUT
trigger.pull = Pull.UP
trigger_state = False

# Potentiometer (unused for dial LEDs)
pot_read = AnalogIn(board.A1)

# Hall effect sensor (49E analog, non-latched, on A0)
sensor = AnalogIn(board.A0)
# Auto-calibrate: read baseline with barrel closed at boot, then set thresholds
# relative to that value. This handles USB vs battery voltage differences.
hall_baseline = sensor.value
HALL_MARGIN = 12000            # how far below baseline = barrel open
HALL_OPEN_THRESHOLD = hall_baseline - HALL_MARGIN        # below this = barrel open
HALL_CLOSED_THRESHOLD = hall_baseline - (HALL_MARGIN - 3000)  # above this = barrel closed
HALL_FIRE_LOCKOUT = 0.5        # ignore hall for 500ms after firing (servo vibration)

# Photocell
photocell = analogio.AnalogIn(board.A2)

# I2S audio
audio = audiobusio.I2SOut(board.I2S_BIT_CLOCK, board.I2S_WORD_SELECT, board.I2S_DATA)
startup = audiocore.WaveFile(open("Startup.wav", "rb"))
shoot = audiocore.WaveFile(open("RayGunPew.wav", "rb"))
reloadOpen = audiocore.WaveFile(open("Reload_Open.wav", "rb"))
reloadClose = audiocore.WaveFile(open("Reload_Close.wav", "rb"))
batteryIn = audiocore.WaveFile(open("battery_in.wav", "rb"))
batteryOut = audiocore.WaveFile(open("battery_out.wav", "rb"))
denied = audiocore.WaveFile(open("denied.wav", "rb"))

# Servo control
pwm = pwmio.PWMOut(board.D4, duty_cycle=2 ** 15, frequency=50)
prop_servo = servo.Servo(pwm)

needle_green = 90   # idle / loaded
needle_yellow = 40  # normal fire
needle_red = 0      # barrel open (max deflection)

prop_servo.angle = needle_green

# External button
switch = DigitalInOut(board.EXTERNAL_BUTTON)
switch.direction = Direction.INPUT
switch.pull = Pull.UP
switch_state = False

# Dial LEDs (always fixed R/Y/G)
dial_pixels = 3
dial = neopixel.NeoPixel(board.D9, dial_pixels)
dial.brightness = 0.8
dial[0] = (255, 0, 0)     # red
dial[1] = (255, 150, 0)   # yellow
dial[2] = (0, 255, 0)     # green
dial.show()

# Fuse pixels (animations)
fuse_pixels = 30  # set to actual number of LEDs
fuse = neopixel.NeoPixel(board.EXTERNAL_NEOPIXELS, fuse_pixels)
fuse.brightness = 0.5

cell = neopixel.NeoPixel(board.D10, 1)
cell.brightness = 1.0
cell[0] = WHITE

blue_wave = SparklePulse(fuse, speed=0.02, period=2, color=BLUE, min_intensity=0.7)
white_wave = SparklePulse(fuse, speed=0.02, period=2, color=WHITE, min_intensity=0.7)
cyan_wave = SparklePulse(fuse, speed=0.02, period=2, color=CYAN, min_intensity=0.7)
red_wave = SparklePulse(fuse, speed=0.02, period=2, color=RED, min_intensity=0.7)
green_wave = SparklePulse(fuse, speed=0.02, period=2, color=GREEN, min_intensity=0.7)

# Onboard LIS3DH accelerometer
HIT_THRESHOLD = 120
i2c = board.I2C()
int1 = DigitalInOut(board.ACCELEROMETER_INTERRUPT)
lis3dh = adafruit_lis3dh.LIS3DH_I2C(i2c, int1=int1)
lis3dh.range = adafruit_lis3dh.RANGE_4_G
lis3dh.set_tap(1, HIT_THRESHOLD)

barrel_open = False
bat = True
bat_changed = False
bat_seq = 0
bat_play_sound = None
photostate = photocell.value
hall_raw = sensor.value
trigger_count = 0
b = 0
hall_last_change = time.monotonic()
HALL_DEBOUNCE = 0.3  # 300ms debounce for hall sensor (filters trigger vibration)
servo_fire_time = 0
last_fire_time = 0
SERVO_MIN_DURATION = 0.35  # 350ms at yellow before auto-return to green
dbg_count = 0

def get_mode(mode):
    if mode <= 100:
        cyan_wave.animate()
    elif mode <= 200:
        red_wave.animate()
    elif mode <= 300:
        green_wave.animate()
    elif mode <= 400:
        blue_wave.animate()
    else:
        white_wave.animate()

def start():
    raw = sensor.value
    print("[STARTUP] hall_raw=%d baseline=%d open_th=%d close_th=%d" % (raw, hall_baseline, HALL_OPEN_THRESHOLD, HALL_CLOSED_THRESHOLD))
    if raw < HALL_OPEN_THRESHOLD:
        audio.play(reloadOpen)
        prop_servo.angle = needle_red
        return True
    else:
        audio.play(startup)
        return False

# Initialize
barrel_open = start()

# Main loop
while True:
    # NeoPixel animation
    reading = pot_read.value
    val = (reading * 500.0) / 65536
    get_mode(val)

    # Read sensors
    hall_raw = sensor.value
    photostate = (photocell.value * 1000) / 65536
    now = time.monotonic()

    # Trigger behavior
    if not trigger.value and not trigger_state and not barrel_open:
        if trigger_count < 19:  # shots 1-19
            audio.play(shoot)
            prop_servo.angle = needle_yellow
            servo_fire_time = now
            last_fire_time = now
            print("[FIRE] cnt=%d angle=%d" % (trigger_count, needle_yellow))
        elif trigger_count == 19:  # 20th shot (out of ammo)
            audio.play(shoot)
            last_fire_time = now
            prop_servo.angle = needle_yellow
        else:  # out of ammo
            audio.play(denied)
        trigger_count += 1
        trigger_state = True

    if trigger.value and trigger_state:
        trigger_state = False
        if trigger_count < 20 and servo_fire_time > 0:
            prop_servo.angle = needle_green
            servo_fire_time = 0

    # Auto-return servo to green
    if servo_fire_time > 0 and (now - servo_fire_time) > SERVO_MIN_DURATION and not barrel_open:
        if trigger_count < 20:
            prop_servo.angle = needle_green
        servo_fire_time = 0

    # Reload behavior (analog hall with hysteresis)
    # Low value = barrel open (magnet far), High value = barrel closed (magnet near)
    if hall_raw < HALL_OPEN_THRESHOLD and not barrel_open and (now - hall_last_change) > HALL_DEBOUNCE and (now - last_fire_time) > HALL_FIRE_LOCKOUT:
        audio.play(reloadOpen)
        prop_servo.angle = needle_red
        barrel_open = True
        hall_last_change = now
        servo_fire_time = 0
        bat_seq = 0
        bat_play_sound = None
        print("[BARREL OPEN] raw=%d" % hall_raw)
    elif hall_raw > HALL_CLOSED_THRESHOLD and barrel_open and (now - hall_last_change) > HALL_DEBOUNCE:
        trigger_count = 0
        b = 0
        bat_seq = 0
        bat_play_sound = None
        audio.play(reloadClose)
        prop_servo.angle = needle_green
        barrel_open = False
        hall_last_change = now
        print("[BARREL CLOSE] raw=%d" % hall_raw)

    # Battery LED + photocell
    dbg_count = (dbg_count + 1) % (5 if barrel_open else 50)
    if dbg_count == 0:
        print("[PHOTO] val=%.0f bat=%s bo=%s b=%d" % (photostate, bat, barrel_open, b))

    if barrel_open:
        if photostate < 200:
            led.value = False
            new_bat = True
        else:
            led.value = True
            new_bat = False
        if new_bat != bat:
            bat_changed = True
            print("[BAT EDGE] new=%s old=%s photo=%.0f bo=%s" % (new_bat, bat, photostate, barrel_open))
        bat = new_bat

    # Battery sound: sequence-based detection
    # Seq 1 (->HIGH): batteryOut | 2 (->LOW): silent | 3 (->HIGH): batteryOut
    # Seq 4 (->LOW): batteryIn  | 5 (->HIGH): silent | 6 (->LOW): batteryIn
    # 7+: silent
    if bat_changed:
        bat_seq += 1
        bat_changed = False
        if bat_seq in (1, 3):
            bat_play_sound = batteryOut
            print("[BAT OUT] seq=%d" % bat_seq)
        elif bat_seq in (4, 6):
            bat_play_sound = batteryIn
            print("[BAT IN] seq=%d" % bat_seq)
        else:
            print("[BAT SILENT] seq=%d" % bat_seq)

    if bat_play_sound and not audio.playing:
        audio.play(bat_play_sound)
        bat_play_sound = None

    time.sleep(0.02)
