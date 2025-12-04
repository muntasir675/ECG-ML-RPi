import os
import sys
import time
import lgpio     # <-- FIX: replace RPi.GPIO

# --- Configuration ---
REQUESTED_FREQ = 250  # Target Hertz
GUARD_DELAY = 0.0005  # 0.5ms delay to prevent stale reads

# LO+ / LO- pins
CHIP = 0
LO_PLUS_PIN = 23
LO_MINUS_PIN = 24


# =====================================================
# STEP 0: GPIO FIX — claim pins even if kernel owns them
# =====================================================

def init_gpio():
    try:
        h = lgpio.gpiochip_open(CHIP)

        # claim inputs with pull-downs (works even if “busy”)
        lgpio.gpio_claim_input(h, LO_PLUS_PIN, lgpio.SET_PULL_DOWN)
        lgpio.gpio_claim_input(h, LO_MINUS_PIN, lgpio.SET_PULL_DOWN)

        return h

    except Exception as e:
        print(f"❌ Failed to claim GPIO pins: {e}")
        sys.exit(1)


def read_lo(h):
    lo_p = lgpio.gpio_read(h, LO_PLUS_PIN)
    lo_m = lgpio.gpio_read(h, LO_MINUS_PIN)
    return lo_p, lo_m


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
    print("❌ ERROR: ADS driver not found!")
    sys.exit(1)
print(f"✅ Found device at: {iio_dev_path}")


# ==========================================
# STEP 2: HARDWARE CONFIGURATION
# ==========================================

# A. Sampling frequency
freq_path = os.path.join(iio_dev_path, "in_voltage0_sampling_frequency")
try:
    if os.path.exists(freq_path):
        with open(freq_path, "w") as f:
            f.write(str(REQUESTED_FREQ))

    with open(freq_path, "r") as f:
        actual_freq = int(f.read().strip())

    print(f"Requested: {REQUESTED_FREQ} | Actual: {actual_freq}")

except Exception as e:
    print(f"⚠️  Frequency set failed ({e}). Defaulting to 128.")
    actual_freq = 128


# B. Scale factor
scale_path = os.path.join(iio_dev_path, "in_voltage0_scale")
try:
    with open(scale_path, "r") as f:
        scale_mv = float(f.read().strip())
except FileNotFoundError:
    print("⚠️ Missing scale file. Using 0.1875")
    scale_mv = 0.1875


# ==========================================
# STEP 3: GPIO CHECK (fixed version)
# ==========================================

h_gpio = init_gpio()

print("\n🔌 Checking Electrodes...")
lo_p, lo_m = read_lo(h_gpio)

if lo_p == 1 or lo_m == 1:
    print("⚠️ WARNING: Electrodes disconnected (LO+/LO-)")
else:
    print("✅ Electrodes Connected.")


# ==========================================
# STEP 4: ACQUISITION LOOP
# ==========================================

print(f"\nStarting Acquisition at {actual_freq} Hz...")
print("Press Ctrl+C to stop\n")

f_adc = open(os.path.join(iio_dev_path, "in_voltage0_raw"), "r")
period = 1.0 / actual_freq
next_wakeup = time.time()
sample_count = 0

try:
    while True:

        # 1. Precise timing
        now = time.time()
        sleep_duration = next_wakeup - now

        if sleep_duration > 0:
            time.sleep(sleep_duration)
        elif sleep_duration < -period:
            skipped = int(abs(sleep_duration) / period)
            next_wakeup += (skipped * period)
            if skipped > 10:
                print(f"⚠️ Skipped {skipped} samples")

        # 2. Guard delay
        time.sleep(GUARD_DELAY)

        # 3. Read ADC
        f_adc.seek(0)
        raw_str = f_adc.read().strip()

        if not raw_str:
            continue

        # GPIO read (lgpio)
        lo_p, lo_m = read_lo(h_gpio)
        timestamp = time.time()

        next_wakeup += period
        sample_count += 1

        # 4. Decimated output
        if sample_count % 50 == 0:
            try:
                raw_val = int(raw_str)
                voltage_mv = raw_val * scale_mv

                ideal_time = next_wakeup - period
                jitter_ms = (timestamp - ideal_time) * 1000

                print(f"[{sample_count}] "
                      f"LO+:{lo_p} LO-:{lo_m} | "
                      f"{raw_val} ({voltage_mv:.2f}mV) | "
                      f"Jitter: {jitter_ms:+.2f}ms")

            except ValueError:
                continue

except KeyboardInterrupt:
    print("\nStopped.")

finally:
    f_adc.close()
    lgpio.gpiochip_close(h_gpio)
