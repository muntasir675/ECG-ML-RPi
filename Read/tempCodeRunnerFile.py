import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import RPi.GPIO as GPIO
import csv
import time
import os
import signal
import sys

# ---------- CONFIGURATION ----------
CSV_FILENAME = "Sensor_read.csv"
TARGET_RATE = 250
ADS_RATE = 475
FIXED_GAIN = 2
LO_PLUS_PIN = 14
LO_MINUS_PIN = 15
ADS_CHANNEL = 0
PRINT_INTERVAL = 0.5

# ---------- SETUP ----------
print("\n=== ECG RECORDER (NO PAUSE) ===")

GPIO.setmode(GPIO.BCM)
GPIO.setup(LO_MINUS_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(LO_PLUS_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c, address=0x48)
ads.gain = FIXED_GAIN
ads.data_rate = ADS_RATE

ecg_channel = AnalogIn(ads, ADS_CHANNEL)

VOLTS_PER_BIT = 2.048 / 32768.0

# ---------- BUFFERS ----------
voltage_buffer = []
raw_buffer = []
ecg_id = None
running = True

# ---------- SIGNAL HANDLER ----------
def cleanup_and_exit(signum, frame):
    global running
    running = False
    print(f"\nSaving...")
    save_data()
    GPIO.cleanup()
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup_and_exit)
signal.signal(signal.SIGTERM, cleanup_and_exit)

# ---------- HELPERS ----------
def get_lead_status():
    try:
        if GPIO.input(LO_PLUS_PIN) or GPIO.input(LO_MINUS_PIN):
            return "❌"
        return "✓"
    except:
        return "?"

def get_next_ecg_id(filename):
    if not os.path.exists(filename): return 0
    try:
        with open(filename, 'r') as f:
            for line in reversed(f.readlines()):
                if line.startswith('v'):
                    return int(line.split(',')[0][1:]) + 1
        return 0
    except: return 0

def init_csv(filename):
    if not os.path.exists(filename):
        with open(filename, 'w', newline='') as f:
            csv.writer(f).writerow(list(range(1000)))

def save_data():
    global voltage_buffer, raw_buffer, ecg_id
    if voltage_buffer:
        with open(CSV_FILENAME, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([f'v{ecg_id}'] + voltage_buffer)
            writer.writerow([f'r{ecg_id}'] + raw_buffer)
        print(f"✓ Saved {len(voltage_buffer)} samples")

# ---------- RECORD ----------
def record_ecg():
    global voltage_buffer, raw_buffer, ecg_id, running
    ecg_id = get_next_ecg_id(CSV_FILENAME)
    sample_count = 0
    delay = 1.0 / TARGET_RATE
    
    print(f"Recording ID {ecg_id} @ 250Hz")
    print("Ctrl+C to stop\n")
    
    start = time.time()
    loop_start = start
    last_print = start

    while running:
        raw = ecg_channel.value
        voltage = raw * VOLTS_PER_BIT
        
        voltage_buffer.append(voltage)
        raw_buffer.append(raw)
        sample_count += 1

        now = time.time()
        if now - last_print >= PRINT_INTERVAL:
            rate = sample_count / (now - start)
            leads = get_lead_status()
            print(f"n={sample_count} | {rate:.1f}Hz | {leads} | {voltage:+.3f}V", end='\r')
            last_print = now

        next_wake = loop_start + (sample_count * delay)
        sleep_time = next_wake - time.time()
        if sleep_time > 0:
            time.sleep(sleep_time)

# ---------- MAIN ----------
if __name__ == "__main__":
    init_csv(CSV_FILENAME)
    record_ecg()
    save_data()
    GPIO.cleanup()
