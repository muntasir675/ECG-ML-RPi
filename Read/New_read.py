import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
from adafruit_ads1x15.ads1x15 import Mode
import csv
import time
import os
import signal
import sys

CSV_FILENAME = "Sensor_read.csv"
ADS_CHANNEL = 0          # A0
PRINT_INTERVAL = 0.1

voltage_buffer = []
raw_buffer = []
ecg_id = None
running = True

i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c, address=0x48)

ads.gain = 1
ads.data_rate = 250
ads.mode = Mode.CONTINUOUS

ecg_channel = AnalogIn(ads, ADS_CHANNEL)

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

def cleanup_and_exit(signum, frame):
    global running
    running = False
    print(f"\nCaught signal {signum}. Saving data...")
    save_data()
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup_and_exit)
signal.signal(signal.SIGTSTP, cleanup_and_exit)
signal.signal(signal.SIGTERM, cleanup_and_exit)

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
            writer.writerow(list(range(1000)))
    else:
        print(f"Appending to existing {filename}")

def save_data():
    global voltage_buffer, raw_buffer, ecg_id
    if voltage_buffer or raw_buffer:
        with open(CSV_FILENAME, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([f'v{ecg_id}'] + voltage_buffer)
            writer.writerow([f'r{ecg_id}'] + raw_buffer)
        voltage_buffer = []
        raw_buffer = []

def record_ecg():
    global voltage_buffer, raw_buffer, ecg_id, running

    ecg_id = get_next_ecg_id(CSV_FILENAME)
    sample_count = 0
    start_time = time.time()
    last_print_time = start_time

    print("\n" + "="*60)
    print(f"RECORDING ECG ID {ecg_id}")
    print(f"Gain: {ads.gain} ({GAIN_SETTINGS[ads.gain]})")
    print(f"ADS data_rate: {ads.data_rate} SPS")
    print("="*60)
    print("Recording started. Press Ctrl+C to stop.\n")

    while running:
        raw = ecg_channel.value
        voltage = raw * get_volts_per_bit()

        voltage_buffer.append(voltage)
        raw_buffer.append(raw)
        sample_count += 1

        now = time.time()
        if now - last_print_time >= PRINT_INTERVAL:
            elapsed = now - start_time
            rate = sample_count / elapsed if elapsed > 0 else 0
            print(
                f"Samples: {sample_count:5d} | Rate: {rate:6.1f} Hz | "
                f"Value: {voltage:+.6f} V (Raw: {raw:6d})",
                end="\r",
                flush=True
            )
            last_print_time = now

        time.sleep(0.001)

def main():
    init_csv(CSV_FILENAME)
    record_ecg()
    save_data()
    print("\nRecording complete.")

if __name__ == "__main__":
    main()
