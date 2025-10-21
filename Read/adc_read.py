import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import RPi.GPIO as GPIO
import csv
import time
import os

# ---------- CONFIGURATION ----------
CSV_FILENAME = "Sensor_read.csv"
SAMPLE_RATE = 100               # Hz
LO_MINUS_PIN = 17
LO_PLUS_PIN  = 27
ADS_CHANNEL = 0
NUM_SAMPLES = 200               # number of samples per recording

# ---------- SETUP ----------
GPIO.setmode(GPIO.BCM)
GPIO.setup([LO_MINUS_PIN, LO_PLUS_PIN], GPIO.IN)

i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c, address=0x48)
ads.gain = 1
ecg_channel = AnalogIn(ads, ADS_CHANNEL)

# ---------- HELPER FUNCTIONS ----------
def leads_off():
    return GPIO.input(LO_PLUS_PIN) or GPIO.input(LO_MINUS_PIN)

def get_next_ecg_id(filename):
    if not os.path.exists(filename):
        return 0
    with open(filename, 'r') as f:
        lines = f.readlines()
        ecg_ids = []
        for line in lines:
            if line.startswith('v') or line.startswith('r'):
                try:
                    ecg_ids.append(int(line.split(',')[0][1:]))
                except:
                    continue
        return max(ecg_ids) + 1 if ecg_ids else 0

def init_csv(filename):
    if not os.path.exists(filename):
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            header = ['ecg_id'] + list(range(NUM_SAMPLES))
            writer.writerow(header)
        print(f"Created CSV file {filename}")
    else:
        print(f"Appending to existing CSV file {filename}")

# ---------- RECORDING ----------
def record_ecg():
    ecg_id = get_next_ecg_id(CSV_FILENAME)
    voltage_buffer = []
    raw_buffer = []
    sampling_delay = 1.0 / SAMPLE_RATE

    print(f"=== Recording ECG ID {ecg_id} ===")
    while leads_off():
        print("⚠️ Electrodes disconnected! Connect them to start.")
        time.sleep(1)

    print("✓ Electrodes connected. Recording... Press Ctrl+C to stop early.")

    for i in range(NUM_SAMPLES):
        while leads_off():
            time.sleep(0.1)  # pause if electrodes disconnect

        voltage = round(ecg_channel.voltage, 4)
        raw = ecg_channel.value
        voltage_buffer.append(voltage)
        raw_buffer.append(raw)
        print(f"Sample {i}: {voltage} V | raw {raw}", end='\r')
        time.sleep(sampling_delay)

    with open(CSV_FILENAME, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([f'v{ecg_id}'] + voltage_buffer)
        writer.writerow([f'r{ecg_id}'] + raw_buffer)

    print(f"\nRecording complete. Saved as v{ecg_id} and r{ecg_id}.")

# ---------- MAIN ----------
def main():
    init_csv(CSV_FILENAME)
    try:
        record_ecg()
    except KeyboardInterrupt:
        print("\nRecording stopped by user.")
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    main()
