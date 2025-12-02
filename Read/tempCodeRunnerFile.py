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
TARGET_RATE = 250           # Target sampling rate in Hz
ADS_RATE = 475              # Set ADC faster than target (475 or 860) to allow overhead
FIXED_GAIN = 2              # Fixed gain (±2.048V) - no more asking
LO_PLUS_PIN = 14            # BCM 14 (Physical 8)
LO_MINUS_PIN = 15           # BCM 15 (Physical 10)
ADS_CHANNEL = 0
PRINT_INTERVAL = 0.2        # Print status every 0.2s

# ---------- STARTUP OPTIONS ----------
# Hardcoded preferences to skip prompts
ignore_leads = False        # Set to True if you want to record even with leads off
invert_lead_logic = False   # Standard logic: 0=Connected, 1=Disconnected

print("\n=== ECG RECORDER (FAST START) ===")

# ---------- SETUP ----------
GPIO.setmode(GPIO.BCM)
GPIO.setup([LO_MINUS_PIN, LO_PLUS_PIN], GPIO.IN)

i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c, address=0x48)
ads.gain = FIXED_GAIN
ads.data_rate = ADS_RATE    # Now 475 SPS to ensure we can actually hit 250 Hz loop

ecg_channel = AnalogIn(ads, ADS_CHANNEL)

# Conversion factors
GAIN_SETTINGS = {
    2/3: (6.144, "±6.144V"),
    1: (4.096, "±4.096V"),
    2: (2.048, "±2.048V"),
    4: (1.024, "±1.024V"),
    8: (0.512, "±0.512V"),
    16: (0.256, "±0.256V")
}

def get_volts_per_bit():
    max_voltage = GAIN_SETTINGS[ads.gain][0]
    return max_voltage / 32768.0

# ---------- GLOBAL BUFFERS ----------
voltage_buffer = []
raw_buffer = []
ecg_id = None
running = True

# ---------- SIGNAL HANDLER ----------
def cleanup_and_exit(signum, frame):
    global running
    running = False
    print(f"\nCaught signal {signum}. Saving data and cleaning up...")
    save_data()
    GPIO.cleanup()
    print("GPIO cleaned up. Exiting.")
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup_and_exit)
signal.signal(signal.SIGTERM, cleanup_and_exit)

# ---------- HELPER FUNCTIONS ----------
def leads_off():
    """Check if any leads are disconnected (High = Off)"""
    return GPIO.input(LO_PLUS_PIN) or GPIO.input(LO_MINUS_PIN)

def get_disconnected_electrodes():
    """Return string describing disconnects"""
    if not leads_off():
        return "Connected ✓"
    
    parts = []
    if GPIO.input(LO_PLUS_PIN): parts.append("LO+ (RA/LA)")
    if GPIO.input(LO_MINUS_PIN): parts.append("LO- (RL)")
    return " & ".join(parts) + " disconnected ❌"

def get_next_ecg_id(filename):
    if not os.path.exists(filename):
        return 0
    try:
        with open(filename, 'r') as f:
            lines = f.readlines()
            ids = []
            for line in lines:
                if line.startswith('v') or line.startswith('r'):
                    try:
                        ids.append(int(line.split(',')[0][1:]))
                    except:
                        continue
            return max(ids) + 1 if ids else 0
    except:
        return 0

def init_csv(filename):
    if not os.path.exists(filename):
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(list(range(1000))) # Header
        print(f"✓ Created {filename}")
    else:
        print(f"✓ Appending to {filename}")

def save_data():
    global voltage_buffer, raw_buffer, ecg_id
    if voltage_buffer or raw_buffer:
        with open(CSV_FILENAME, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([f'v{ecg_id}'] + voltage_buffer)
            writer.writerow([f'r{ecg_id}'] + raw_buffer)
        print(f"\n✓ Saved {len(voltage_buffer)} samples as v{ecg_id} / r{ecg_id}")
        voltage_buffer = []
        raw_buffer = []

# ---------- RECORDING FUNCTION ----------
def record_ecg():
    global voltage_buffer, raw_buffer, ecg_id, running
    ecg_id = get_next_ecg_id(CSV_FILENAME)
    sample_count = 0
    sampling_delay = 1.0 / TARGET_RATE
    
    print(f"\n{'='*40}")
    print(f"RECORDING ID: {ecg_id}")
    print(f"Target: {TARGET_RATE} Hz (ADC Rate: {ADS_RATE} SPS)")
    print(f"Gain: {ads.gain} ({GAIN_SETTINGS[ads.gain][1]})")
    print(f"{'='*40}\n")
    
    # Initial connection check
    if not ignore_leads and leads_off():
        print("⏳ Waiting for electrodes...")
        while leads_off() and running:
            print(f"⚠️ {get_disconnected_electrodes()}   ", end='\r', flush=True)
            time.sleep(0.5)
    
    print("\n✓ Recording! Press Ctrl+C to stop.")
    
    start_time = time.time()
    last_print_time = start_time
    loop_start = start_time
    
    volts_per_bit = get_volts_per_bit()

    while running:
        # Check leads
        if not ignore_leads and leads_off():
            print(f"\n⚠️ {get_disconnected_electrodes()} - Paused...")
            while leads_off() and running:
                time.sleep(0.1)
            if running:
                print("✓ Resuming...                   ")
                # Reset timing to avoid fast-forwarding
                loop_start = time.time() - (sample_count * sampling_delay)

        # Read Sample
        raw = ecg_channel.value
        voltage = raw * volts_per_bit
        
        voltage_buffer.append(voltage)
        raw_buffer.append(raw)
        sample_count += 1

        # Print Status
        curr_time = time.time()
        if curr_time - last_print_time >= PRINT_INTERVAL:
            elapsed = curr_time - start_time
            rate = sample_count / elapsed if elapsed > 0 else 0
            print(f"Samples: {sample_count:5d} | Rate: {rate:5.1f} Hz | Val: {voltage:+.4f}V", end='\r', flush=True)
            last_print_time = curr_time

        # Precise Timing
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
    print("\nDone.")
