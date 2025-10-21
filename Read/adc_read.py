import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import RPi.GPIO as GPIO
import csv
import time
import os
from datetime import datetime

# ---------- CONFIGURATION ----------
CSV_FILENAME = "ecg_data.csv"
SAMPLE_RATE = 200               # Hz
LO_MINUS_PIN = 17               # GPIO for LO-
LO_PLUS_PIN  = 27               # GPIO for LO+
ADS_CHANNEL = 0                 # A0 channel on ADS1115

# ---------- SETUP ----------
GPIO.setmode(GPIO.BCM)
GPIO.setup([LO_MINUS_PIN, LO_PLUS_PIN], GPIO.IN)

i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c, address=0x48)
ads.gain = 1
ecg_channel = AnalogIn(ads, ADS_CHANNEL)

# ---------- HELPER FUNCTIONS ----------
def leads_off():
    """Return True if electrodes are disconnected"""
    return GPIO.input(LO_PLUS_PIN) or GPIO.input(LO_MINUS_PIN)

def get_next_ecg_id(filename):
    """Get the next ECG ID from CSV"""
    if not os.path.exists(filename):
        return 1
    with open(filename, 'r') as f:
        reader = csv.reader(f)
        rows = list(reader)
        if len(rows) <= 1:  # only header
            return 1
        last_row = rows[-1]
        return int(last_row[0]) + 1

def init_csv(filename):
    """Create CSV with header if it doesn't exist"""
    if not os.path.exists(filename):
        with open(filename, 'w', newline='') as f:
            header = ['ecg_id', 'timestamp', 'voltage']
            csv.writer(f).writerow(header)
        print(f"Created new CSV file: {filename}")
    else:
        print(f"Appending to existing CSV file: {filename}")

# ---------- MAIN RECORDING FUNCTION ----------
def record_ecg():
    ecg_id = get_next_ecg_id(CSV_FILENAME)
    sampling_delay = 1.0 / SAMPLE_RATE
    print(f"\n=== Recording ECG ID {ecg_id} ===")
    print(f"Sample rate: {SAMPLE_RATE} Hz")
    print("Waiting for electrodes to connect...")

    while leads_off():
        print("⚠️ Electrodes disconnected! Please attach electrodes.")
        time.sleep(1)

    print("✓ Electrodes connected. Starting in 1 second...")
    time.sleep(1)

    start_time = time.time()
    sample_count = 0

    with open(CSV_FILENAME, 'a', newline='') as f:
        writer = csv.writer(f)

        while True:
            if leads_off():
                print("\n⚠️ Electrodes disconnected! Pausing recording...")
                while leads_off():
                    time.sleep(0.1)
                print("✓ Electrodes reconnected. Resuming...")

            voltage = ecg_channel.voltage
            timestamp = datetime.now().isoformat()
            writer.writerow([ecg_id, timestamp, round(voltage, 4)])
            print(f"Sample {sample_count}: {voltage:.4f} V", end='\r')
            sample_count += 1

            # maintain sampling rate
            elapsed = time.time() - start_time
            time.sleep(max(0, sampling_delay - (elapsed % sampling_delay)))

# ---------- MAIN ----------
def main():
    print("\n=== AD8232 ECG Logger ===")
    print(f"Started at {datetime.now()}")
    init_csv(CSV_FILENAME)

    try:
        record_ecg()
    except KeyboardInterrupt:
        print("\nRecording stopped by user.")
    finally:
        GPIO.cleanup()
        print("GPIO cleaned up. Exiting.")

if __name__ == "__main__":
    main()
