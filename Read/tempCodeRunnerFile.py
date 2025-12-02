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
TARGET_RATE = 250           # Hz target
ADS_RATE = 475              # Set ADC faster than target to allow headroom
FIXED_GAIN = 2              # Fixed gain (±2.048V)
LO_PLUS_PIN = 14            # BCM 14
LO_MINUS_PIN = 15           # BCM 15
ADS_CHANNEL = 0
PRINT_INTERVAL = 0.5        # Update screen text every 0.5s
CHECK_LEADS_EVERY = 50      # Only check leads every 50 samples (debounce)

# ---------- SETUP ----------
print("\n=== ECG RECORDER (DEBOUNCED) ===")

GPIO.setmode(GPIO.BCM)
GPIO.setup([LO_MINUS_PIN, LO_PLUS_PIN], GPIO.IN)

i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c, address=0x48)
ads.gain = FIXED_GAIN
ads.data_rate = ADS_RATE

ecg_channel = AnalogIn(ads, ADS_CHANNEL)

# Conversion factors
GAIN_SETTINGS = { 2: (2.048, "±2.048V") }

def get_volts_per_bit():
    return GAIN_SETTINGS[FIXED_GAIN][0] / 32768.0

# ---------- GLOBAL BUFFERS ----------
voltage_buffer = []
raw_buffer = []
ecg_id = None
running = True

# ---------- SIGNAL HANDLER ----------
def cleanup_and_exit(signum, frame):
    global running
    running = False
    print(f"\nCaught signal {signum}. Saving data...")
    save_data()
    GPIO.cleanup()
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup_and_exit)
signal.signal(signal.SIGTERM, cleanup_and_exit)

# ---------- HELPER FUNCTIONS ----------
def leads_off():
    """Check if any leads are disconnected (High = Off)"""
    return GPIO.input(LO_PLUS_PIN) or GPIO.input(LO_MINUS_PIN)

def get_next_ecg_id(filename):
    if not os.path.exists(filename): return 0
    try:
        with open(filename, 'r') as f:
            # Quick logic to find last ID
            for line in reversed(f.readlines()):
                if line.startswith('v'):
                    return int(line.split(',')[0][1:]) + 1
        return 0
    except: return 0

def init_csv(filename):
    if not os.path.exists(filename):
        with open(filename, 'w', newline='') as f:
            csv.writer(f).writerow(list(range(1000)))
        print(f"✓ Created {filename}")

def save_data():
    global voltage_buffer, raw_buffer, ecg_id
    if voltage_buffer:
        with open(CSV_FILENAME, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([f'v{ecg_id}'] + voltage_buffer)
            writer.writerow([f'r{ecg_id}'] + raw_buffer)
        print(f"✓ Saved {len(voltage_buffer)} samples (ID: {ecg_id})")

# ---------- RECORDING FUNCTION ----------
def record_ecg():
    global voltage_buffer, raw_buffer, ecg_id, running
    ecg_id = get_next_ecg_id(CSV_FILENAME)
    sample_count = 0
    sampling_delay = 1.0 / TARGET_RATE
    volts_per_bit = get_volts_per_bit()
    
    print(f"recording ID {ecg_id} at ~{TARGET_RATE} Hz...")
    print("Use Ctrl+C to stop.\n")
    
    # Initial Check
    if leads_off():
        print("⚠️  Check leads... (waiting)")
        while leads_off() and running: time.sleep(0.2)
        print("✓ Connected. Starting.")

    start_time = time.time()
    loop_start = start_time
    last_print = start_time

    while running:
        # --- 1. CHECK LEADS (Only every N samples) ---
        if sample_count % CHECK_LEADS_EVERY == 0:
            if leads_off():
                print(f"\n⚠️  Leads Disconnected! Pausing...")
                save_data() # Save what we have so far
                voltage_buffer = [] # Clear buffers
                raw_buffer = []
                
                while leads_off() and running:
                    time.sleep(0.2)
                
                print("✓ Reconnected. Resuming...")
                # Reset timing so we don't 'catch up' the pause duration
                loop_start = time.time() - (sample_count * sampling_delay)

        # --- 2. READ SAMPLE ---
        raw = ecg_channel.value
        voltage = raw * volts_per_bit
        
        voltage_buffer.append(voltage)
        raw_buffer.append(raw)
        sample_count += 1

        # --- 3. PRINT STATUS ---
        now = time.time()
        if now - last_print >= PRINT_INTERVAL:
            elapsed = now - start_time
            rate = sample_count / elapsed if elapsed > 0 else 0
            print(f"Samples: {sample_count} | Rate: {rate:.1f} Hz | {voltage:+.3f}V", end='\r', flush=True)
            last_print = now

        # --- 4. TIMING ---
        next_wake = loop_start + (sample_count * sampling_delay)
        sleep_dur = next_wake - time.time()
        if sleep_dur > 0:
            time.sleep(sleep_dur)

# ---------- MAIN ----------
if __name__ == "__main__":
    init_csv(CSV_FILENAME)
    record_ecg()
    save_data()
    GPIO.cleanup()
