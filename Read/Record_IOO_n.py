import os
import sys
import time
import csv
from datetime import datetime
import RPi.GPIO as GPIO

# --- Configuration ---
REQUESTED_FREQ = 250      # Target Hertz
GUARD_DELAY = 0.0005      # 0.5ms delay to prevent stale reads
# LO_PLUS_PIN = 14          # GPIO 14
# LO_MINUS_PIN = 15         # GPIO 15
LO_PLUS_PIN = 23
LO_MINUS_PIN = 24
CSV_FILENAME = f"ecg_data_{datetime.now().strftime('%d-%m-%Y_at_%I-%M%p')}.csv"
BUFFER_SIZE = 250         # Write every 250 samples (~1s at 250 Hz)

# ==========================================
# STEP 1: AUTO-DETECT DRIVER
# ==========================================
def find_iio_device(device_name_part="ads1115"):
    base_path = "/sys/bus/iio/devices"
    if not os.path.exists(base_path):
        return None
    for dirname in os.listdir(base_path):
        if dirname.startswith("iio:device"):
            full_path = os.path.join(base_path, dirname)
            name_file = os.path.join(full_path, "name")
            if os.path.exists(name_file):
                with open(name_file, "r") as f:
                    if device_name_part in f.read().strip().lower():
                        return full_path
    return None

# iio_dev_path = find_iio_device("ads1115")
iio_dev_path = find_iio_device("ads1015")
if not iio_dev_path:
    print("❌ ERROR: ADS1115 driver not found!")
    sys.exit(1)
print(f"✅ Found ADS1115 at: {iio_dev_path}")

# ==========================================
# STEP 2: HARDWARE CONFIGURATION
# ==========================================
# A. Set Frequency
freq_path = os.path.join(iio_dev_path, "in_voltage0_sampling_frequency")
try:
    if os.path.exists(freq_path):
        with open(freq_path, "w") as f:
            f.write(str(REQUESTED_FREQ))

    with open(freq_path, "r") as f:
        actual_freq = int(f.read().strip())

    print(f"   Requested: {REQUESTED_FREQ} SPS | Actual: {actual_freq} SPS")
    if actual_freq != REQUESTED_FREQ:
        print(f"⚠️  Note: Loop adjusted to match hardware ({actual_freq} Hz).")

except Exception as e:
    print(f"⚠️  Warning: Frequency set failed ({e}). Defaulting to 128 Hz.")
    actual_freq = 128

# B. Get Scale Factor
scale_path = os.path.join(iio_dev_path, "in_voltage0_scale")
try:
    with open(scale_path, "r") as f:
        scale_mv = float(f.read().strip())
except FileNotFoundError:
    print("⚠️  CRITICAL: Scale file missing! Using unsafe default (0.1875).")
    scale_mv = 0.1875

# ==========================================
# STEP 3: GPIO SETUP & CHECK
# ==========================================
GPIO.setmode(GPIO.BCM)
GPIO.setup(LO_PLUS_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(LO_MINUS_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

print("\n🔌 Checking Electrodes...")
if GPIO.input(LO_PLUS_PIN) == 1 or GPIO.input(LO_MINUS_PIN) == 1:
    print("⚠️  WARNING: Electrodes disconnected! (Check LO+ / LO-)")
else:
    print("✅ Electrodes Connected.")

# ==========================================
# STEP 4: CSV SETUP
# ==========================================
print(f"\n💾 Saving data to: {CSV_FILENAME}")
with open(CSV_FILENAME, mode="w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Timestamp", "LO_plus", "LO_minus", "Raw_ADC", "Voltage_mV"])

data_buffer = []

# ==========================================
# STEP 5: ACQUISITION LOOP
# ==========================================
print(f"\nStarting Acquisition at {actual_freq} Hz...")
print("Press Ctrl+C to stop")

f_adc = open(os.path.join(iio_dev_path, "in_voltage0_raw"), "r")
period = 1.0 / actual_freq
next_wakeup = time.time()
sample_count = 0

try:
    while True:
        # --- 1. PRECISE SLEEP ---
        now = time.time()
        sleep_duration = next_wakeup - now

        if sleep_duration > 0:
            time.sleep(sleep_duration)
        elif sleep_duration < -period:
            skipped = int(abs(sleep_duration) / period)
            next_wakeup += (skipped * period)
            if skipped > 10:
                print(f"⚠️ Skipped {skipped} samples")

        # --- 2. GUARD DELAY ---
        time.sleep(GUARD_DELAY)

        # --- 3. FAST CAPTURE ---
        f_adc.seek(0)
        raw_str = f_adc.read().strip()
        if not raw_str:
            next_wakeup += period
            continue

        lo_p = GPIO.input(LO_PLUS_PIN)
        lo_m = GPIO.input(LO_MINUS_PIN)
        timestamp = time.time()

        # --- 4. UPDATE TIMING ---
        next_wakeup += period
        sample_count += 1

        # --- 5. BUFFER DATA FOR CSV ---
        try:
            raw_val = int(raw_str)
            voltage_mv = raw_val * scale_mv
            data_buffer.append([timestamp, lo_p, lo_m, raw_val, f"{voltage_mv:.3f}"])
        except ValueError:
            continue

        if len(data_buffer) >= BUFFER_SIZE:
            with open(CSV_FILENAME, mode="a", newline="") as f:
                writer = csv.writer(f)
                writer.writerows(data_buffer)
            data_buffer.clear()

        # --- 6. DECIMATED TERMINAL OUTPUT ---
        if sample_count % 50 == 0:
            ideal_time = next_wakeup - period
            jitter_ms = (timestamp - ideal_time) * 1000
            print(f"[{sample_count}] LO+:{lo_p} LO-:{lo_m} | {raw_val} ({voltage_mv:.2f}mV) | Jitter: {jitter_ms:+.2f}ms")

except KeyboardInterrupt:
    if data_buffer:
        with open(CSV_FILENAME, mode="a", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(data_buffer)
    print("\nStopped.")
finally:
    f_adc.close()
    GPIO.cleanup()
