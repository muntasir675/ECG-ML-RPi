import os
import re
import sys
import time
import csv
import struct
from datetime import datetime
import RPi.GPIO as GPIO

# ==========================================
# Configuration
# ==========================================
REQUESTED_HZ = 250
BUFFER_LEN = 2000
ENABLE_TIMESTAMP = True
LO_PLUS_PIN = 23
LO_MINUS_PIN = 24
CSV_FILENAME = f"ecg_A0_buffer_{datetime.now().strftime('%d-%m-%Y_at_%I-%M%p')}.csv"

SYSFS_IIO = "/sys/bus/iio/devices"

# ==========================================
# Helpers
# ==========================================
def rtxt(p):
    with open(p, "r") as f:
        return f.read().strip()

def wtxt(p, s):
    with open(p, "w") as f:
        f.write(str(s))

def find_ads_iio_dev():
    for d in os.listdir(SYSFS_IIO):
        if not d.startswith("iio:device"):
            continue
        dp = os.path.join(SYSFS_IIO, d)
        namep = os.path.join(dp, "name")
        if os.path.exists(namep):
            n = rtxt(namep).lower()
            if "ads1115" in n or "ads1015" in n:
                return dp, d
    return None, None

def find_trigger(prefer_substr="hrtimer"):
    for d in os.listdir(SYSFS_IIO):
        if not d.startswith("trigger"):
            continue
        tp = os.path.join(SYSFS_IIO, d)
        namep = os.path.join(tp, "name")
        if os.path.exists(namep):
            nm = rtxt(namep)
            if prefer_substr in nm.lower():
                return tp, nm
    for d in os.listdir(SYSFS_IIO):
        if d.startswith("trigger"):
            tp = os.path.join(SYSFS_IIO, d)
            namep = os.path.join(tp, "name")
            if os.path.exists(namep):
                return tp, rtxt(namep)
    return None, None

def parse_iio_type(type_str):
    # Example: "le:s16/16>>0" [web:66]
    m = re.match(r"^(le|be):([us])(\d+)/(\d+)>>(\d+)$", type_str)
    if not m:
        raise RuntimeError(f"Unrecognized IIO type: {type_str}")
    endian, sign, bits, storage, shift = m.groups()
    bits, storage, shift = int(bits), int(storage), int(shift)
    if storage % 8 != 0:
        raise RuntimeError(f"Storagebits not byte-aligned: {type_str}")
    return endian, sign, bits, storage, shift, storage // 8

def unpack_int(endian, sign, size_bytes, b):
    fmt_end = "<" if endian == "le" else ">"
    if size_bytes == 2:
        fmt = fmt_end + ("H" if sign == "u" else "h")
    elif size_bytes == 4:
        fmt = fmt_end + ("I" if sign == "u" else "i")
    elif size_bytes == 8:
        fmt = fmt_end + ("Q" if sign == "u" else "q")
    else:
        raise RuntimeError(f"Unsupported size: {size_bytes}")
    return struct.unpack(fmt, b)[0]

# ==========================================
# Setup GPIO for electrode detection
# ==========================================
GPIO.setmode(GPIO.BCM)
GPIO.setup(LO_PLUS_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(LO_MINUS_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

print("🔌 Checking Electrodes...")
if GPIO.input(LO_PLUS_PIN) == 1 or GPIO.input(LO_MINUS_PIN) == 1:
    print("⚠️  WARNING: Electrodes disconnected! (Check LO+ / LO-)")
else:
    print("✅ Electrodes Connected.")

# ==========================================
# Locate IIO device
# ==========================================
dev_path, dev_name = find_ads_iio_dev()
if not dev_path:
    print("❌ ADS1115 IIO device not found.")
    GPIO.cleanup()
    sys.exit(1)

scan_dir = os.path.join(dev_path, "scan_elements")
buf_dir  = os.path.join(dev_path, "buffer")
trig_dir = os.path.join(dev_path, "trigger")

# ==========================================
# Fixed A0 channel selection
# ==========================================
A0_CH = "in_voltage0"
A0_EN = os.path.join(scan_dir, f"{A0_CH}_en")
A0_TY = os.path.join(scan_dir, f"{A0_CH}_type")
A0_SCALE = os.path.join(dev_path, f"{A0_CH}_scale")

if not os.path.exists(A0_EN) or not os.path.exists(A0_TY):
    print(f"❌ {A0_CH} scan element not present.")
    GPIO.cleanup()
    sys.exit(1)

a0_type = rtxt(A0_TY)
endian, sign, bits, storage, shift, a0_size = parse_iio_type(a0_type)

# Check data type (ADS1115 typically reports signed for single-ended)
if sign == "u":
    print(f"⚠️ Unusual: {A0_CH} reports unsigned (type={a0_type})")
else:
    print(f"✅ {A0_CH} type: {a0_type} (signed, normal for ADS1115)")

# Read scale (mV per LSB, as reported by IIO driver)
try:
    scale_mv = float(rtxt(A0_SCALE)) if os.path.exists(A0_SCALE) else 1.0
except:
    scale_mv = 1.0
    print("⚠️  Could not read scale; defaulting to 1.0")

print(f"✅ Using scale: {scale_mv} mV/LSB (from IIO driver, accounts for PGA gain)")

# ==========================================
# Disable buffer (safe reconfiguration)
# ==========================================
try:
    if os.path.exists(os.path.join(buf_dir, "enable")):
        wtxt(os.path.join(buf_dir, "enable"), 0)
except:
    pass

# ==========================================
# Enable only A0 channel
# ==========================================
for fn in os.listdir(scan_dir):
    if fn.endswith("_en"):
        wtxt(os.path.join(scan_dir, fn), 0)
wtxt(A0_EN, 1)

# ==========================================
# Optional timestamp channel
# ==========================================
ts_size = 0
ts_endian = "le"
ts_sign = "s"
if ENABLE_TIMESTAMP and os.path.exists(os.path.join(scan_dir, "in_timestamp_en")):
    wtxt(os.path.join(scan_dir, "in_timestamp_en"), 1)
    ts_type = rtxt(os.path.join(scan_dir, "in_timestamp_type"))
    ts_endian, ts_sign, _, _, _, ts_size = parse_iio_type(ts_type)

# ==========================================
# Attach trigger
# ==========================================
trig_path, trig_name = find_trigger("hrtimer")
if trig_name and os.path.exists(os.path.join(trig_dir, "current_trigger")):
    wtxt(os.path.join(trig_dir, "current_trigger"), trig_name)
    if trig_path and os.path.exists(os.path.join(trig_path, "sampling_frequency")):
        wtxt(os.path.join(trig_path, "sampling_frequency"), REQUESTED_HZ)
    print(f"✅ Trigger: {trig_name} @ {REQUESTED_HZ} Hz")
else:
    print("⚠️  No trigger found. Buffer will not capture samples.")
    print("    Load iio-trig-hrtimer: sudo modprobe iio-trig-hrtimer")

# ==========================================
# Configure and enable buffer
# ==========================================
if os.path.exists(os.path.join(buf_dir, "length")):
    wtxt(os.path.join(buf_dir, "length"), BUFFER_LEN)
wtxt(os.path.join(buf_dir, "enable"), 1)

devnode = f"/dev/{dev_name}"
rec_size = a0_size + ts_size

print(f"✅ Device: {dev_name}")
print(f"✅ Channel: {A0_CH} type={a0_type} bytes={a0_size}")
print(f"✅ Devnode: {devnode} record_bytes={rec_size}")
print(f"💾 Saving to: {CSV_FILENAME}\n")

# ==========================================
# Acquisition loop
# ==========================================
with open(CSV_FILENAME, "w", newline="") as fcsv:
    w = csv.writer(fcsv)
    w.writerow(["Timestamp", "LO_plus", "LO_minus", "Raw_ADC", "Voltage_mV"])

    fd = os.open(devnode, os.O_RDONLY)
    sample_count = 0
    
    try:
        print("Starting acquisition... Press Ctrl+C to stop\n")
        
        while True:
            data = os.read(fd, rec_size * 64)
            if not data:
                time.sleep(0.001)
                continue

            usable = len(data) - (len(data) % rec_size)
            
            for off in range(0, usable, rec_size):
                # Parse raw ADC value
                raw_bytes = data[off:off + a0_size]
                raw = unpack_int(endian, sign, a0_size, raw_bytes)

                # Convert to voltage using IIO scale (handles signed values correctly)
                voltage_mv = raw * scale_mv

                # Read current GPIO state (lead-off detection)
                lo_p = GPIO.input(LO_PLUS_PIN)
                lo_m = GPIO.input(LO_MINUS_PIN)

                # Timestamp: use kernel timestamp if available, else userspace time
                if ts_size:
                    ts_bytes = data[off + a0_size: off + rec_size]
                    ts_ns = unpack_int(ts_endian, ts_sign, ts_size, ts_bytes)
                    timestamp = ts_ns / 1e9  # Convert nanoseconds to seconds
                else:
                    timestamp = time.time()

                # Write to CSV
                w.writerow([timestamp, lo_p, lo_m, raw, f"{voltage_mv:.3f}"])
                sample_count += 1

                # Periodic console output
                if sample_count % 50 == 0:
                    print(f"[{sample_count}] LO+:{lo_p} LO-:{lo_m} | RAW:{raw} ({voltage_mv:.2f} mV)")

    except KeyboardInterrupt:
        print("\n\nStopped.")
    
    finally:
        os.close(fd)
        try:
            wtxt(os.path.join(buf_dir, "enable"), 0)
        except:
            pass
        GPIO.cleanup()
        print(f"✅ Data saved to {CSV_FILENAME}")