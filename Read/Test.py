import os
import sys
import time
import RPi.GPIO as GPIO

# --- Configuration ---
TARGET_FREQ = 250  # Hertz
LO_PLUS_PIN = 14   # GPIO 14 (Leads Off +)
LO_MINUS_PIN = 15  # GPIO 15 (Leads Off -)

# ==========================================
# STEP 1: AUTO-DETECT ADS1115
# ==========================================
def find_iio_device(device_name_part="ads1115"):
    """Finds the IIO device path by checking the driver name."""
    base_path = "/sys/bus/iio/devices"
    
    if not os.path.exists(base_path):
        return None

    for dirname in os.listdir(base_path):
        if dirname.startswith("iio:device"):
            full_path = os.path.join(base_path, dirname)
            name_file = os.path.join(full_path, "name")
            
            if os.path.exists(name_file):
                with open(name_file, "r") as f:
                    driver_name = f.read().strip().lower()
                
                if device_name_part in driver_name:
                    return full_path
    return None

# Locate the device
iio_dev_path = find_iio_device("ads1115")

if not iio_dev_path:
    print("❌ ERROR: ADS1115 driver not found!")
    print("   Possible Causes:")
    print("   1. Overlay not enabled in /boot/config.txt (add dtoverlay=ads1115)")
    print("   2. Wiring issue (Check SDA/SCL)")
    print("   3. Driver loaded as different name (ti-ads1015?)")
    sys.exit(1)

print(f"✅ Found ADS1115 at: {iio_dev_path}")


# ==========================================
# STEP 2: GPIO SETUP
# ==========================================
GPIO.setmode(GPIO.BCM)
GPIO.setup(LO_PLUS_PIN, GPIO.IN)
GPIO.setup(LO_MINUS_PIN, GPIO.IN)


# ==========================================
# STEP 3: CONFIGURE FREQUENCY
# ==========================================
try:
    freq_path = os.path.join(iio_dev_path, "in_voltage0_sampling_frequency")
    
    if os.path.exists(freq_path):
        # Write target frequency
        with open(freq_path, "w") as f:
            f.write(str(TARGET_FREQ))
        
        # Read back actual frequency (Driver might round to 128, 250, 475, etc.)
        with open(freq_path, "r") as f:
            actual_freq = f.read().strip()
        print(f"   Sampling Rate Configured: {actual_freq} SPS")
    else:
        print("ℹ️  Info: Frequency control file not found (using default).")

except OSError:
    print("⚠️  Warning: Could not set frequency (Permission denied? Driver locked?)")


# ==========================================
# STEP 4: DRIFT-FREE ACQUISITION LOOP
# ==========================================
print(f"\nStarting Acquisition at {TARGET_FREQ} Hz...")
print("Press Ctrl+C to stop")

try:
    # Pre-open the raw value file for efficiency
    f_adc = open(os.path.join(iio_dev_path, "in_voltage0_raw"), "r")
    
    # Optional: Read Scale (Volts per unit)
    # with open(os.path.join(iio_dev_path, "in_voltage0_scale"), "r") as f:
    #     scale = float(f.read().strip())

    # --- Timing Setup ---
    period = 1.0 / TARGET_FREQ
    next_wakeup = time.time()

    while True:
        # 1. Wait for the exact next 4ms tick
        # This calculates "sleep time = target_time - current_time"
        # If processing took 1ms, it sleeps 3ms. If processing took 0.1ms, it sleeps 3.9ms.
        next_wakeup += period
        sleep_duration = next_wakeup - time.time()
        
        if sleep_duration > 0:
            time.sleep(sleep_duration)
        else:
            # If we are late (negative sleep), don't sleep at all to catch up
            # But prevents 'next_wakeup' from falling infinitely behind
            if sleep_duration < -0.1: # If more than 100ms behind, reset time base
                 next_wakeup = time.time()

        # 2. Read ADC (Reset pointer -> Read)
        f_adc.seek(0)
        raw_adc_str = f_adc.read().strip()
        
        # 3. Read GPIO
        lo_plus = GPIO.input(LO_PLUS_PIN)
        lo_minus = GPIO.input(LO_MINUS_PIN)
        
        # 4. Print Data
        print(f"LO+: {lo_plus} | LO-: {lo_minus} | ADC: {raw_adc_str}")

except KeyboardInterrupt:
    print("\nStopping...")

finally:
    f_adc.close()
    GPIO.cleanup()
