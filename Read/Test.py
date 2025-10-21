import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import RPi.GPIO as GPIO
import time
import signal
import sys

# --- GPIO setup (safe default) ---
GPIO.setmode(GPIO.BCM)

def cleanup_and_exit(signum, frame):
    print(f"\nCaught signal {signum}. Cleaning up GPIO and exiting...")
    GPIO.cleanup()
    sys.exit(0)

# Catch Ctrl+C, Ctrl+Z
signal.signal(signal.SIGINT, cleanup_and_exit)
signal.signal(signal.SIGTSTP, cleanup_and_exit)
signal.signal(signal.SIGTERM, cleanup_and_exit)

# --- ADC setup ---
i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c, address=0x48)
ads.gain = 1
chan = AnalogIn(ads, 0)

# --- Main loop ---
while True:
    print(f"Raw: {chan.value} | Voltage: {chan.voltage:.4f}V", end='\r')
    time.sleep(0.1)
