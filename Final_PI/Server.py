import os
import socket
import subprocess
import signal
import sys
import time
from flask import Flask, jsonify, send_file, request
import shutil
import json
from datetime import datetime

# Get the absolute path of the directory where the server script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

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
        def cleanup(self, *args, **kwargs): pass
        def setwarnings(self, *args, **kwargs): pass
    GPIO = MockGPIO()

app = Flask(__name__)

# File Paths
ECG_FILE = os.path.join(SCRIPT_DIR, "ecg_data_pi.csv")
SEGMENT_FILE = os.path.join(SCRIPT_DIR, "ecg_segment.csv")
FEATURES_FILE = os.path.join(SCRIPT_DIR, "ecg_features_pi.csv")
POINTS_FILE = os.path.join(SCRIPT_DIR, "ecg_points_pi.csv")
PROCESSED_ECG_FILE = os.path.join(SCRIPT_DIR, "ecg_processed_pi.csv")
DIAGNOSIS_FILE = os.path.join(SCRIPT_DIR, "ecg_diagnosis_pi.csv")
DEBUG_ECG_FILE = os.path.join(SCRIPT_DIR, "Recordings/ecg_data_muntasir2.csv")
STATUS_FILE = os.path.join(SCRIPT_DIR, "recording_status.json")
RECORDINGS_DIR = os.path.join(SCRIPT_DIR, "Recordings")
SDN_PIN = 25

debug_mode = False
recording_process = None

# --- FILE MANAGEMENT ---
def cleanup_temp_files(archive_name=None):
    """Archive raw ECG with a custom name and clean up all generated files."""
    # Create recordings directory if it doesn't exist
    if not os.path.exists(RECORDINGS_DIR):
        os.makedirs(RECORDINGS_DIR)
        
    # Archive the raw recording if it exists
    if os.path.exists(ECG_FILE):
        # Determine the final filename for the archive
        if archive_name:
            # Sanitize the provided filename to prevent security issues like path traversal
            safe_name = "".join(c for c in archive_name if c.isalnum() or c in (' ', '_', '-')).rstrip()
            # If the sanitized name is empty (e.g., all invalid chars), fall back to a timestamp
            if not safe_name:
                safe_name = f"ecg_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            final_filename = f"{safe_name}.csv"
        else:
            # Default to a timestamped filename if no name is provided
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            final_filename = f"ecg_data_{timestamp}.csv"

        archive_path = os.path.join(RECORDINGS_DIR, final_filename)
        try:
            shutil.copy2(ECG_FILE, archive_path)
        except Exception as e:
            print(f"Failed to archive ECG file: {e}")

    files = [ECG_FILE, SEGMENT_FILE, FEATURES_FILE, POINTS_FILE, PROCESSED_ECG_FILE, DIAGNOSIS_FILE, STATUS_FILE]
    for f in files:
        if os.path.exists(f):
            os.remove(f)
            
# --- SERVER MODE CONTROL ---
@app.route("/set_mode", methods=['POST'])
def set_mode():
    """Sets the server to 'regular' or 'debug' mode."""
    global debug_mode
    data = request.get_json()
    if not data or 'mode' not in data:
        return jsonify(error="Missing 'mode' in request body"), 400
    
    mode = data['mode']
    if mode == 'debug':
        debug_mode = True
        return jsonify(success=True, message="Mode set to debug.")
    elif mode == 'regular':
        debug_mode = False
        return jsonify(success=True, message="Mode set to regular.")
    else:
        return jsonify(error="Invalid mode. Must be 'debug' or 'regular'."), 400

# --- APP CONTROLLED RECORDING ---
@app.route("/start_recording")
def start_recording():
    """Starts a recording or prepares the debug file."""
    global recording_process, debug_mode
    if recording_process and recording_process.poll() is None:
        return jsonify(error="Recording already in progress"), 409
    
    if debug_mode:
        try:
            if not os.path.exists(DEBUG_ECG_FILE):
                return jsonify(error=f"Debug file not found: {DEBUG_ECG_FILE}"), 404
            # In debug mode, just copy the file and we're "done"
            cleanup_temp_files()
            shutil.copy2(DEBUG_ECG_FILE, ECG_FILE)
            return jsonify(success=True, message="Debug mode: ECG data file created.", file=ECG_FILE)
        except Exception as e:
            return jsonify(error=str(e)), 500
    else:
        # Regular hardware recording
        try:
            # Power on the ADC
            GPIO.output(SDN_PIN, GPIO.HIGH)
            time.sleep(0.1) # Allow ADC to stabilize

            # Start Record_IOO_n.py with duration 0 (infinite)
            script_path = os.path.join(SCRIPT_DIR, "Record_IOO_n.py")
            recording_process = subprocess.Popen(
                [sys.executable, script_path, "--duration", "0"],
                cwd=SCRIPT_DIR
            )

            # Wait briefly to see if the process fails immediately
            time.sleep(0.5)

            if recording_process.poll() is not None: # The process has terminated
                error_message = "Recording script failed on startup."
                # Try to get a more specific error from the status file
                if os.path.exists(STATUS_FILE):
                    try:
                        with open(STATUS_FILE, 'r') as f:
                            status_data = json.load(f)
                            error_message = status_data.get("error", error_message)
                    except Exception:
                        pass
                return jsonify(error=error_message), 500

            return jsonify(success=True, pid=recording_process.pid, message="Recording started.")
        except Exception as e:
            return jsonify(error=str(e)), 500

@app.route("/stop_recording")
def stop_recording():
    global recording_process
    if not recording_process or recording_process.poll() is not None:
        return jsonify(error="No recording in progress"), 400
    
    try:
        # Send SIGTERM to allow graceful exit (closing files)
        recording_process.terminate()
        try:
            recording_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            recording_process.kill()
        
        recording_process = None
        
        # Power off the ADC
        GPIO.output(SDN_PIN, GPIO.LOW)

        # Rename the generated timestamped file to the standard ECG_FILE
        csv_files = [f for f in os.listdir(SCRIPT_DIR) if f.startswith('ecg_data_') and f.endswith('.csv')]
        if csv_files:
            # Construct full paths for file operations
            latest_file_name = max(csv_files, key=lambda f: os.path.getctime(os.path.join(SCRIPT_DIR, f)))
            latest_filepath = os.path.join(SCRIPT_DIR, latest_file_name)
            if os.path.exists(ECG_FILE):
                os.remove(ECG_FILE)
            os.rename(latest_filepath, ECG_FILE)
            return jsonify(success=True, file=ECG_FILE)
        else:
            return jsonify(error="No recording file found"), 500
            
    except Exception as e:
        return jsonify(error=str(e)), 500

# --- STATUS ---
@app.route("/status")
def get_status():
    """Gets the current status of the device (recording, debug mode, lead status)."""
    global recording_process, debug_mode
    is_recording = recording_process is not None and recording_process.poll() is None
    
    status_data = {
        "recording": is_recording,
        "debug_mode": debug_mode
    }

    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, 'r') as f:
                file_status = json.load(f)
                status_data.update(file_status)
        except (json.JSONDecodeError, IOError):
            pass # Ignore if file is being written or is empty
        
    return jsonify(status_data)

# --- SEGMENT UPLOAD ---
@app.route("/upload_segment", methods=['POST'])
def upload_segment():
    try:
        if 'file' not in request.files:
            return jsonify(error="No file provided"), 400
        
        file = request.files['file']
        file.save(SEGMENT_FILE)
        return jsonify(success=True)
    except Exception as e:
        return jsonify(error=str(e)), 500

# --- EXTRACTION ---
@app.route("/extract")
def extract():
    try:
        input_file = SEGMENT_FILE if os.path.exists(SEGMENT_FILE) else ECG_FILE
        
        if not os.path.exists(input_file):
            return jsonify(error="ECG file missing"), 404
        
        script_path = os.path.join(SCRIPT_DIR, "Extract_tmp.py")
        if not os.path.exists(script_path):
            return jsonify(error="Extract_tmp.py not found"), 404
        
        result = subprocess.run([
            sys.executable, script_path,
            "--input", input_file,
            "--output", FEATURES_FILE,
            "--points-output", POINTS_FILE,
            "--processed-output", PROCESSED_ECG_FILE
        ], capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            return jsonify(error=f"Extraction failed: {result.stderr}"), 500
        
        return jsonify(success=True)
    except Exception as e:
        return jsonify(error=str(e)), 500

# --- DIAGNOSIS ---
@app.route("/diagnose")
def diagnose():
    try:
        if not os.path.exists(FEATURES_FILE):
            return jsonify(error="Features file missing"), 404
        
        script_path = os.path.join(SCRIPT_DIR, "RP_tmp.py")
        if not os.path.exists(script_path):
            return jsonify(error="RP_tmp.py not found"), 404
        
        # The model files are in the same directory as the scripts.
        MODEL_DIR = SCRIPT_DIR
        
        result = subprocess.run([
            sys.executable, script_path,
            "--input", FEATURES_FILE,
            "--output", DIAGNOSIS_FILE,
            "--model-dir", MODEL_DIR
        ], capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            return jsonify(error=f"Diagnosis failed: {result.stderr}"), 500
        
        return send_file(DIAGNOSIS_FILE, as_attachment=True)
    except Exception as e:
        return jsonify(error=str(e)), 500

# --- CLEANUP ---
@app.route("/cleanup", methods=['GET', 'POST'])
def cleanup():
    try:
        archive_name = None
        # Check for a filename if the request is POST with JSON
        if request.method == 'POST':
            data = request.get_json()
            if data and 'filename' in data:
                archive_name = data.get('filename')

        cleanup_temp_files(archive_name=archive_name)
        return jsonify(status="success")
    except Exception as e:
        return jsonify(error=str(e)), 500

# --- DOWNLOAD ---
@app.route("/download/<filename>")
def download_file(filename):
    files = {
        "ecg": ECG_FILE,
        "features": FEATURES_FILE,
        "points": POINTS_FILE,
        "diagnosis": DIAGNOSIS_FILE,
        "processed": PROCESSED_ECG_FILE
    }
    
    if filename not in files or not os.path.exists(files[filename]):
        return "File not found", 404
    
    return send_file(files[filename], as_attachment=True)

if __name__ == "__main__":
    def get_ip_address():
        """Gets the primary IP address of the machine."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Doesn't have to be reachable
            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1' # Fallback
        finally:
            s.close()
        return IP

    # The server will run in regular mode by default.
    # Debug mode can be enabled by setting the `debug_mode` variable to True.
    debug_mode = False

    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(SDN_PIN, GPIO.OUT, initial=GPIO.LOW)
    try:
        hostname = socket.gethostname()
        ip_address = get_ip_address()
        print(f"--- Server starting on http://{hostname} ({ip_address}:8000) ---")
        try:
            from waitress import serve
            serve(app, host="0.0.0.0", port=8000, threads=4)
        except ImportError:
            app.run(host="0.0.0.0", port=8000, threaded=True, debug=False)
    finally:
        GPIO.cleanup()
