import os
import sys
import time
import csv
from datetime import datetime
import RPi.GPIO as GPIO

# --- Configuration ---
REQUESTED_FREQ = 250
GUARD_DELAY = 0.0005
LO_PLUS_PIN = 23
LO_MINUS_PIN = 24
BUFFER_SIZE = 250

# Global variables
iio_dev_path = None
actual_freq = None
scale_mv = None

def find_iio_device(device_name_part="ads1015"):
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

def initialize_hardware():
    global iio_dev_path, actual_freq, scale_mv
    
    iio_dev_path = find_iio_device("ads1015")
    if not iio_dev_path:
        raise Exception("ADS1015 driver not found!")
    
    # Configure frequency
    freq_path = os.path.join(iio_dev_path, "in_voltage0_sampling_frequency")
    try:
        if os.path.exists(freq_path):
            with open(freq_path, "w") as f:
                f.write(str(REQUESTED_FREQ))
        with open(freq_path, "r") as f:
            actual_freq = int(f.read().strip())
    except Exception as e:
        actual_freq = 128
    
    # Get scale
    scale_path = os.path.join(iio_dev_path, "in_voltage0_scale")
    try:
        with open(scale_path, "r") as f:
            scale_mv = float(f.read().strip())
    except FileNotFoundError:
        scale_mv = 0.1875
    
    # Setup GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(LO_PLUS_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(LO_MINUS_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    
    return actual_freq, scale_mv

def check_lead_status():
    """Check if electrodes are connected"""
    lo_p = GPIO.input(LO_PLUS_PIN)
    lo_m = GPIO.input(LO_MINUS_PIN)
    return {
        'lo_plus': lo_p,
        'lo_minus': lo_m,
        'disconnected': lo_p == 1 or lo_m == 1
    }

def record_ecg(duration=10, output_filename=None):
    """Record ECG with precise timing and lead-off detection"""
    global iio_dev_path, actual_freq, scale_mv
    
    if not iio_dev_path:
        initialize_hardware()
    
    if output_filename is None:
        output_filename = f"ecg_data_{datetime.now().strftime('%d-%m-%Y_at_%I-%M%p')}.csv"
    
    # Check leads before starting
    lead_status = check_lead_status()
    if lead_status['disconnected']:
        raise Exception(f"Electrodes disconnected: LO+={lead_status['lo_plus']}, LO-={lead_status['lo_minus']}")
    
    print(f"💾 Recording to: {output_filename}")
    
    # Initialize CSV
    with open(output_filename, mode="w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "LO_plus", "LO_minus", "Raw_ADC", "Voltage_mV"])
    
    data_buffer = []
    f_adc = open(os.path.join(iio_dev_path, "in_voltage0_raw"), "r")
    
    period = 1.0 / actual_freq
    next_wakeup = time.time()
    sample_count = 0
    start_time = time.time()
    
    try:
        while (time.time() - start_time) < duration:
            # Precise sleep
            now = time.time()
            sleep_duration = next_wakeup - now
            
            if sleep_duration > 0:
                time.sleep(sleep_duration)
            elif sleep_duration < -period:
                skipped = int(abs(sleep_duration) / period)
                next_wakeup += (skipped * period)
                if skipped > 10:
                    print(f"⚠️ Skipped {skipped} samples")
            
            # Guard delay
            time.sleep(GUARD_DELAY)
            
            # Fast capture
            f_adc.seek(0)
            raw_str = f_adc.read().strip()
            if not raw_str:
                next_wakeup += period
                continue
            
            lo_p = GPIO.input(LO_PLUS_PIN)
            lo_m = GPIO.input(LO_MINUS_PIN)
            timestamp = time.time() - start_time
            
            # Update timing
            next_wakeup += period
            sample_count += 1
            
            # Buffer data
            try:
                raw_val = int(raw_str)
                voltage_mv = raw_val * scale_mv
                data_buffer.append([timestamp, lo_p, lo_m, raw_val, f"{voltage_mv:.3f}"])
            except ValueError:
                continue
            
            # Write buffer periodically
            if len(data_buffer) >= BUFFER_SIZE:
                with open(output_filename, mode="a", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerows(data_buffer)
                data_buffer.clear()
            
            # Decimated output
            if sample_count % 50 == 0:
                ideal_time = next_wakeup - period
                jitter_ms = ((time.time()) - ideal_time) * 1000
                print(f"[{sample_count}] LO+:{lo_p} LO-:{lo_m} | {raw_val} ({voltage_mv:.2f}mV) | Jitter: {jitter_ms:+.2f}ms")
        
        # Write remaining buffer
        if data_buffer:
            with open(output_filename, mode="a", newline="") as f:
                writer = csv.writer(f)
                writer.writerows(data_buffer)
        
        print(f"✅ Recording complete: {sample_count} samples")
        return output_filename
        
    except Exception as e:
        print(f"❌ Recording error: {e}")
        raise
    finally:
        f_adc.close()

def cleanup():
    """Clean up GPIO"""
    GPIO.cleanup()

# If run directly (for testing)
if __name__ == "__main__":
    try:
        initialize_hardware()
        print(f"✅ Hardware initialized: {actual_freq} Hz")
        filename = record_ecg(duration=10)
        print(f"✅ Saved to: {filename}")
    finally:
        cleanup()
