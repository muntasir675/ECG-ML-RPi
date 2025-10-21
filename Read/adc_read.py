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
SAMPLE_RATE = 100           # Hz
LO_PLUS_PIN = 14  # physical pin 8
LO_MINUS_PIN = 15 # physical pin 10
ADS_CHANNEL = 0

# ---------- STARTUP OPTION ----------
ignore_leads = False
user_input = input("Ignore lead disconnects? (y/N): ").strip().lower()
if user_input == 'y':
    ignore_leads = True
    print("⚠️ Will ignore lead disconnects.")
else:
    print("✓ Will check leads normally.")

# ---------- SETUP ----------
GPIO.setmode(GPIO.BCM)
GPIO.setup([LO_MINUS_PIN, LO_PLUS_PIN], GPIO.IN)

i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c, address=0x48)
ads.gain = 1
ecg_channel = AnalogIn(ads, ADS_CHANNEL)

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

signal.signal(signal.SIGINT, cleanup_and_exit)   # Ctrl+C
signal.signal(signal.SIGTSTP, cleanup_and_exit)  # Ctrl+Z
signal.signal(signal.SIGTERM, cleanup_and_exit)  # kill command

# ---------- HELPER FUNCTIONS ----------
def leads_off():
    return GPIO.input(LO_PLUS_PIN) or GPIO.input(LO_MINUS_PIN)

def get_next_ecg_id(filename):
    if not os.path.exists(filename):
        return 0
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

def init_csv(filename):
    if not os.path.exists(filename):
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(list(range(1000)))  # Only numbers, no "sample_"
        print(f"Created CSV file {filename}")
    else:
        print(f"Appending to existing CSV file {filename}")

def save_data():
    global voltage_buffer, raw_buffer, ecg_id
    if voltage_buffer or raw_buffer:
        with open(CSV_FILENAME, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([f'v{ecg_id}'] + voltage_buffer)
            writer.writerow([f'r{ecg_id}'] + raw_buffer)
        print(f"Saved {len(voltage_buffer)} samples as v{ecg_id} / r{ecg_id}")
        voltage_buffer = []
        raw_buffer = []

# ---------- RECORDING FUNCTION ----------
def record_ecg():
    global voltage_buffer, raw_buffer, ecg_id, running
    ecg_id = get_next_ecg_id(CSV_FILENAME)
    sample_count = 0
    sampling_delay = 1.0 / SAMPLE_RATE

    print(f"=== Recording ECG ID {ecg_id} ===")
    if not ignore_leads:
        print("Waiting for electrodes to connect...")
        while leads_off() and running:
            print("⚠️ Electrodes disconnected! Connect them to start.")
            time.sleep(1)

    print("✓ Recording started. Press Ctrl+C to stop.")

    while running:
        if not ignore_leads and leads_off():
            print("\n⚠️ Electrodes disconnected! Pausing recording...")
            while leads_off() and running:
                time.sleep(0.1)
            if running:
                print("✓ Electrodes reconnected. Resuming...")

        # voltage = round(ecg_channel.voltage, 4)
        voltage = ecg_channel.voltage  # keep full float precision
        raw = ecg_channel.value

        voltage_buffer.append(voltage)
        raw_buffer.append(raw)
        print(f"Sample {sample_count}: {voltage} V | raw {raw}", end='\r')
        sample_count += 1
        time.sleep(sampling_delay)

# ---------- MAIN ----------
def main():
    init_csv(CSV_FILENAME)
    record_ecg()  # runs until signal interrupts
    save_data()
    GPIO.cleanup()
    print("Exiting.")

if __name__ == "__main__":
    main()
