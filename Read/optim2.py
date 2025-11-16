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
TARGET_RATE = 300           # Hz target
LO_PLUS_PIN = 14  # physical pin 8
LO_MINUS_PIN = 15 # physical pin 10
ADS_CHANNEL = 0
PRINT_INTERVAL = 0.1  # Print every 0.1 seconds

# ---------- STARTUP OPTIONS ----------
ignore_leads = False
invert_lead_logic = False
auto_gain = True
check_leads_interval = 100  # Check leads every N samples (not every sample)

print("\n=== ECG RECORDER WITH DIAGNOSTICS ===")
print("This will help identify connection issues\n")

user_input = input("Run hardware diagnostics first? (Y/n): ").strip().lower()
run_diagnostics = user_input != 'n'

user_input = input("Ignore lead disconnects? (y/N): ").strip().lower()
if user_input == 'y':
    ignore_leads = True
    print("⚠️ Will ignore lead disconnects.")
else:
    print("✓ Will check leads normally.")

user_input = input("Invert lead detection logic? (y/N): ").strip().lower()
if user_input == 'y':
    invert_lead_logic = True
    print("⚠️ Using inverted lead detection logic.")

user_input = input("Auto-test different gain settings? (Y/n): ").strip().lower()
if user_input == 'n':
    auto_gain = False

user_input = input("Check leads every N samples (50-500, default 100): ").strip()
if user_input.isdigit():
    check_leads_interval = int(user_input)
    print(f"✓ Will check leads every {check_leads_interval} samples")

# ---------- SETUP ----------
GPIO.setmode(GPIO.BCM)
GPIO.setup([LO_MINUS_PIN, LO_PLUS_PIN], GPIO.IN)

i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c, address=0x48)
ads.gain = 2/3  # Start with ±6.144V range (widest range)
ads.data_rate = 860  # Max sampling rate for ADS1115

ecg_channel = AnalogIn(ads, ADS_CHANNEL)

# Conversion factors for different gains
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
signal.signal(signal.SIGTSTP, cleanup_and_exit)
signal.signal(signal.SIGTERM, cleanup_and_exit)

# ---------- HELPER FUNCTIONS ----------
def leads_off():
    """Check if leads are disconnected with debouncing"""
    lo_plus = GPIO.input(LO_PLUS_PIN)
    lo_minus = GPIO.input(LO_MINUS_PIN)
    
    if invert_lead_logic:
        # Inverted: Leads OFF when both are LOW
        return not (lo_plus or lo_minus)
    else:
        # Normal: Leads OFF when either is HIGH
        return lo_plus or lo_minus

def leads_off_debounced(check_count=5, check_delay=0.002):
    """Check if leads are disconnected with debouncing to avoid false triggers"""
    disconnected_count = 0
    for _ in range(check_count):
        if leads_off():
            disconnected_count += 1
        time.sleep(check_delay)
    
    # Consider disconnected only if majority of checks fail
    return disconnected_count >= (check_count // 2 + 1)

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
        print(f"✓ Created CSV file {filename}")
    else:
        print(f"✓ Appending to existing CSV file {filename}")

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

# ---------- DIAGNOSTIC FUNCTIONS ----------
def diagnose_hardware():
    """Run comprehensive hardware diagnostics"""
    print("\n" + "="*60)
    print("HARDWARE DIAGNOSTICS")
    print("="*60)
    
    # 1. Check GPIO pins
    print("\n1. LEAD-OFF DETECTION PINS:")
    print(f"   LO+ Pin {LO_PLUS_PIN} (BCM): {GPIO.input(LO_PLUS_PIN)} {'(HIGH)' if GPIO.input(LO_PLUS_PIN) else '(LOW)'}")
    print(f"   LO- Pin {LO_MINUS_PIN} (BCM): {GPIO.input(LO_MINUS_PIN)} {'(HIGH)' if GPIO.input(LO_MINUS_PIN) else '(LOW)'}")
    print(f"   Lead Status: {'DISCONNECTED ❌' if leads_off() else 'CONNECTED ✓'}")
    
    # 2. Check ADC readings
    print(f"\n2. ADC READINGS (Channel {ADS_CHANNEL}):")
    print(f"   Current Gain: {ads.gain} ({GAIN_SETTINGS[ads.gain][1]})")
    print(f"   Sampling 50 values over 2.5 seconds...")
    print(f"   (Looking for heartbeat pattern...)")
    
    raw_values = []
    for i in range(50):
        raw = ecg_channel.value
        voltage = ecg_channel.voltage
        raw_values.append(raw)
        if i < 3 or i >= 47:  # Show first and last 3
            print(f"   Sample {i+1:2d}: Raw={raw:6d} | Voltage={voltage:+.6f}V")
        elif i == 3:
            print("   ...")
        time.sleep(0.05)
    
    # 3. Analyze readings
    avg_raw = sum(raw_values) / len(raw_values)
    min_raw = min(raw_values)
    max_raw = max(raw_values)
    range_raw = max_raw - min_raw
    
    print(f"\n3. SIGNAL ANALYSIS:")
    print(f"   Average: {avg_raw:6.0f}")
    print(f"   Min:     {min_raw:6d}")
    print(f"   Max:     {max_raw:6d}")
    print(f"   Range:   {range_raw:6d}")
    
    # 4. Diagnosis
    print(f"\n4. DIAGNOSIS:")
    if range_raw < 10:
        print("   ⚠️  FLAT LINE - No signal variation detected")
        print("   Possible causes:")
        print("      - Electrodes not connected to skin")
        print("      - AD8232 OUTPUT not connected to ADS1115")
        print("      - AD8232 not powered (check 3.3V)")
        print("      - Wrong ADS1115 channel selected")
    elif abs(avg_raw) > 30000:
        print("   ⚠️  SATURATED - Signal at extreme values")
        print("   Possible causes:")
        print("      - Electrodes disconnected (rail-to-rail)")
        print("      - Gain setting too high")
        print("      - AD8232 output issue")
    elif range_raw < 200:
        print("   ⚠️  NO HEARTBEAT DETECTED - Signal at baseline")
        print("   Hardware is working but no ECG signal present!")
        print("   ")
        print("   ELECTRODE TROUBLESHOOTING:")
        print("   1. Clean skin with rubbing alcohol, let dry")
        print("   2. Remove old electrodes, use fresh ones")
        print("   3. Press electrodes FIRMLY for 10+ seconds")
        print("   4. Wait 1-2 minutes for gel to hydrate skin")
        print("   5. Try these positions:")
        print("      • RA: Below RIGHT collarbone")
        print("      • LA: Below LEFT collarbone")
        print("      • RL: Right lower abdomen")
        print("   6. Hold breath briefly, then breathe normally")
        print("   7. Stay still, relax muscles")
    elif range_raw < 500:
        print("   ⚠️  WEAK ECG SIGNAL")
        print("   Some variation detected but signal is weak.")
        print("   Try better electrode contact or different placement.")
    else:
        print("   ✓ Good ECG signal detected!")
        print(f"   Signal variation: {range_raw} LSB")
    
    print("\n" + "="*60 + "\n")

def test_gain_settings():
    """Test different gain settings to find optimal one"""
    print("\n" + "="*60)
    print("AUTO-GAIN TESTING")
    print("="*60)
    
    gain_results = {}
    
    for gain_val in [2/3, 1, 2, 4, 8, 16]:
        ads.gain = gain_val
        time.sleep(0.1)  # Let ADC settle
        
        print(f"\nTesting gain {gain_val} ({GAIN_SETTINGS[gain_val][1]})...")
        
        raw_values = []
        for _ in range(20):
            raw_values.append(ecg_channel.value)
            time.sleep(0.02)
        
        avg = sum(raw_values) / len(raw_values)
        range_val = max(raw_values) - min(raw_values)
        
        gain_results[gain_val] = {
            'avg': avg,
            'range': range_val,
            'saturated': abs(avg) > 30000 or max(raw_values) >= 32760 or min(raw_values) <= -32760
        }
        
        print(f"   Range: {range_val:5d} | Avg: {avg:6.0f} | {'SATURATED ❌' if gain_results[gain_val]['saturated'] else 'OK ✓'}")
    
    # Find best gain
    best_gain = None
    best_range = 0
    
    for gain_val, results in gain_results.items():
        if not results['saturated'] and results['range'] > best_range:
            best_gain = gain_val
            best_range = results['range']
    
    if best_gain:
        ads.gain = best_gain
        print(f"\n✓ RECOMMENDED GAIN: {best_gain} ({GAIN_SETTINGS[best_gain][1]})")
        print(f"  Signal range: {best_range} LSB")
    else:
        ads.gain = 2/3
        print(f"\n⚠️ All gains show issues, using {ads.gain} ({GAIN_SETTINGS[ads.gain][1]})")
    
    print("="*60 + "\n")

# ---------- RECORDING FUNCTION ----------
def record_ecg():
    global voltage_buffer, raw_buffer, ecg_id, running
    ecg_id = get_next_ecg_id(CSV_FILENAME)
    sample_count = 0
    sampling_delay = 1.0 / TARGET_RATE
    last_print_time = time.time()
    start_time = time.time()

    print(f"\n{'='*60}")
    print(f"RECORDING ECG ID {ecg_id}")
    print(f"Target Rate: {TARGET_RATE} Hz")
    print(f"Gain: {ads.gain} ({GAIN_SETTINGS[ads.gain][1]})")
    print(f"Lead check interval: Every {check_leads_interval} samples")
    print(f"{'='*60}\n")
    
    if not ignore_leads:
        print("⏳ Waiting for electrodes to connect...")
        while leads_off() and running:
            lo_plus = GPIO.input(LO_PLUS_PIN)
            lo_minus = GPIO.input(LO_MINUS_PIN)
            print(f"⚠️ Electrodes disconnected! LO+={lo_plus} LO-={lo_minus}", end='\r', flush=True)
            time.sleep(0.5)

    print("\n✓ Recording started. Press Ctrl+C to stop.")
    print("💡 TIP: Lead checks happen periodically, not every sample (reduces false triggers)")
    loop_start = time.time()

    while running:
        # Only check leads periodically, not every sample
        if not ignore_leads and sample_count % check_leads_interval == 0:
            if leads_off_debounced():
                print("\n⚠️ Electrodes disconnected! Pausing recording...")
                while leads_off_debounced() and running:
                    time.sleep(0.1)
                if running:
                    print("✓ Electrodes reconnected. Resuming...")
                    loop_start = time.time()

        # Read raw value (single I2C transaction)
        raw = ecg_channel.value
        voltage = raw * get_volts_per_bit()

        voltage_buffer.append(voltage)
        raw_buffer.append(raw)
        sample_count += 1

        # Print status
        current_time = time.time()
        if current_time - last_print_time >= PRINT_INTERVAL:
            elapsed = current_time - start_time
            actual_rate = sample_count / elapsed if elapsed > 0 else 0
            print(f"📊 Samples: {sample_count:5d} | Rate: {actual_rate:6.1f} Hz | Value: {voltage:+.6f}V (Raw: {raw:6d})", end='\r', flush=True)
            last_print_time = current_time

        # Timing control
        next_sample_time = loop_start + (sample_count * sampling_delay)
        sleep_time = next_sample_time - time.time()
        if sleep_time > 0:
            time.sleep(sleep_time)

# ---------- MAIN ----------
def main():
    print("\n")
    init_csv(CSV_FILENAME)
    
    if run_diagnostics:
        diagnose_hardware()
        
        if auto_gain:
            test_gain_settings()
        
        print("\nDiagnostics complete!")
        user_input = input("Continue to recording? (Y/n): ").strip().lower()
        if user_input == 'n':
            print("Exiting.")
            GPIO.cleanup()
            return
    
    record_ecg()
    save_data()
    GPIO.cleanup()
    print("\n\n✓ Recording complete. Exiting.")

if __name__ == "__main__":
    main()