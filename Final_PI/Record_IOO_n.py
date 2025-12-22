import os
import sys
import time
import csv
import json
import signal
import argparse
from datetime import datetime

try:
    import RPi.GPIO as GPIO
except (RuntimeError, ImportError):
    # Create a mock GPIO object for development on non-Pi systems
    class MockGPIO:
        BCM = None
        OUT = None
        IN = None
        HIGH = None
        LOW = None
        PUD_DOWN = None
        def setmode(self, *args, **kwargs): pass
        def setup(self, *args, **kwargs): pass
        def output(self, *args, **kwargs): pass
        def input(self, *args, **kwargs): return 0
        def cleanup(self, *args, **kwargs): pass
    GPIO = MockGPIO()

# --- Configuration ---
REQUESTED_FREQ = 250
GUARD_DELAY = 0.0005
LO_PLUS_PIN = 24
LO_MINUS_PIN = 23
BUFFER_SIZE = 250

# Get the absolute path of the directory where the script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE = os.path.join(SCRIPT_DIR, "recording_status.json")

# Global variables
iio_dev_path = None
actual_freq = None
scale_mv = None
stop_requested = False

def signal_handler(signum, frame):
    global stop_requested
    stop_requested = True

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
        raise Exception("ADS1015 IIO driver not found!")

    # Configure frequency
    freq_path = os.path.join(iio_dev_path, "in_voltage0_sampling_frequency")
    freq_avail_path = os.path.join(iio_dev_path, "in_voltage0_sampling_frequency_available")

    if not os.path.exists(freq_path):
        raise IOError(f"Sampling frequency file not found at {freq_path}")

    try:
        with open(freq_path, "w") as f:
            f.write(str(REQUESTED_FREQ))
        with open(freq_path, "r") as f:
            actual_freq = int(f.read().strip())
    except Exception as e:
        available = "Not found"
        if os.path.exists(freq_avail_path):
            with open(freq_avail_path, 'r') as f_avail:
                available = f_avail.read().strip()
        raise IOError(f"Failed to set sampling frequency. Error: {e}. Available: {available}")

    if actual_freq != REQUESTED_FREQ:
        available = "Not found"
        if os.path.exists(freq_avail_path):
            with open(freq_avail_path, 'r') as f_avail:
                available = f_avail.read().strip()
        raise ValueError(
            f"Driver rejected {REQUESTED_FREQ}Hz. Actual is {actual_freq}Hz. Available: {available}"
        )

    # Get scale
    scale_path = os.path.join(iio_dev_path, "in_voltage0_scale")
    try:
        with open(scale_path, "r") as f:
            scale_mv = float(f.read().strip())
    except (FileNotFoundError, ValueError) as e:
        raise IOError(f"Could not read a valid ADC scale from {scale_path}: {e}")

    # Setup GPIO
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

def update_live_status(lead_status):
    """Write current lead status to file for live monitoring"""
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump({
                "connected": not lead_status['disconnected'],
                "lo_plus": lead_status['lo_plus'],
                "lo_minus": lead_status['lo_minus']
            }, f)
    except Exception:
        pass

def record_ecg(duration=0, output_filename=None):
    """Record ECG with precise timing and lead-off detection"""
    global iio_dev_path, actual_freq, scale_mv
    
    if not iio_dev_path:
        initialize_hardware()

    # Register signal handlers for graceful stopping
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    if output_filename is None:
        timestamped_filename = f"ecg_data_{datetime.now().strftime('%d-%m-%Y_at_%I-%M%p')}.csv"
        output_filepath = os.path.join(SCRIPT_DIR, timestamped_filename)
    else:
        output_filepath = os.path.join(SCRIPT_DIR, output_filename)
    
    # Check leads before starting
    lead_status = check_lead_status()
    update_live_status(lead_status)
    
    # Initialize CSV
    with open(output_filepath, mode="w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "LO_plus", "LO_minus", "Raw_ADC", "Voltage_mV"])
    
    data_buffer = []
    f_adc = open(os.path.join(iio_dev_path, "in_voltage0_raw"), "r")
    
    period = 1.0 / actual_freq
    next_wakeup = time.time()
    sample_count = 0
    start_time = time.time()
    
    error_occurred = False
    try:
        # Run while not stopped. If duration > 0, also check time. If duration == 0, run forever.
        while not stop_requested and (duration <= 0 or (time.time() - start_time) < duration):
            # Precise sleep
            now = time.time()
            sleep_duration = next_wakeup - now
            
            if sleep_duration > 0:
                time.sleep(sleep_duration)
            elif sleep_duration < -period:
                skipped = int(abs(sleep_duration) / period)
                next_wakeup += (skipped * period)
            
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
                with open(output_filepath, mode="a", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerows(data_buffer)
                data_buffer.clear()
            
            # Decimated output for status update
            if sample_count % 250 == 0:
                # Update live status file every ~1s
                update_live_status({
                    'disconnected': lo_p == 1 or lo_m == 1,
                    'lo_plus': lo_p,
                    'lo_minus': lo_m
                })
        
        # Write remaining buffer
        if data_buffer:
            with open(output_filepath, mode="a", newline="") as f:
                writer = csv.writer(f)
                writer.writerows(data_buffer)
        return output_filepath
        
    except Exception as e:
        error_occurred = True
        # On error, write the failure status for the server to pick up.
        try:
            with open(STATUS_FILE, 'w') as f:
                json.dump({"recording": False, "error": str(e)}, f)
        except Exception:
            pass # If we can't write the status, just exit.
        raise
    finally:
        f_adc.close()
        # Only remove the status file on a clean, requested stop.
        # On an error, the file is left for the server to diagnose the issue.
        if not error_occurred and os.path.exists(STATUS_FILE):
            os.remove(STATUS_FILE)

def cleanup():
    """Clean up GPIO"""
    GPIO.cleanup()

# If run directly (for testing)
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Record ECG')
    parser.add_argument('--duration', type=float, default=10, help='Duration in seconds (0 for infinite)')
    parser.add_argument('--output', type=str, default=None, help='Output filename')
    parser.add_argument('--no-sdn', action='store_true', help='Do not control SDN (GPIO 25) pin')
    args = parser.parse_args()

    # Setup GPIO for standalone testing
    GPIO.setmode(GPIO.BCM)
    try:
        # Power on the ADC if testing standalone (assuming SDN is on GPIO 25)
        if not args.no_sdn:
            GPIO.setup(25, GPIO.OUT, initial=GPIO.HIGH)
        initialize_hardware()
        filename = record_ecg(duration=args.duration, output_filename=args.output)
    finally:
        GPIO.cleanup()
