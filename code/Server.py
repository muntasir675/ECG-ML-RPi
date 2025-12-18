import os
import socket
import subprocess
import sys
from flask import Flask, jsonify, send_file, request
import shutil

app = Flask(__name__)

# File Paths
ECG_FILE = "ecg_data_pi.csv"
SEGMENT_FILE = "ecg_segment.csv"
FEATURES_FILE = "ecg_features_pi.csv"
POINTS_FILE = "ecg_points_pi.csv"
PROCESSED_ECG_FILE = "ecg_processed_pi.csv"
DIAGNOSIS_FILE = "ecg_diagnosis_pi.csv"
DEBUG_ECG_FILE = "ecg_data_debug.csv"

debug_mode = False

# --- FILE MANAGEMENT ---
def cleanup_temp_files():
    """Clean up all generated files except debug CSV"""
    files = [ECG_FILE, SEGMENT_FILE, FEATURES_FILE, POINTS_FILE, PROCESSED_ECG_FILE, DIAGNOSIS_FILE]
    for f in files:
        if os.path.exists(f):
            os.remove(f)

# --- RECORDING ---
@app.route("/record")
def record():
    try:
        if debug_mode:
            if not os.path.exists(DEBUG_ECG_FILE):
                return jsonify(error=f"Debug file not found: {DEBUG_ECG_FILE}"), 404
            shutil.copy2(DEBUG_ECG_FILE, ECG_FILE)
        else:
            result = subprocess.run([
                sys.executable, "Record_IOO_n.py"
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                return jsonify(error=f"Recording failed: {result.stderr}"), 500
            
            csv_files = [f for f in os.listdir('.') if f.startswith('ecg_data_') and f.endswith('.csv')]
            if csv_files:
                latest_file = max(csv_files, key=os.path.getctime)
                os.rename(latest_file, ECG_FILE)
        
        return send_file(ECG_FILE, as_attachment=True)
    except Exception as e:
        return jsonify(error=str(e)), 500

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
        
        if not os.path.exists("Extract_tmp.py"):
            return jsonify(error="Extract_tmp.py not found"), 404
        
        result = subprocess.run([
            sys.executable, "Extract_tmp.py",
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
        
        if not os.path.exists("RP_tmp.py"):
            return jsonify(error="RP_tmp.py not found"), 404
        
        MODEL_DIR = "/home/pi/Desktop/raspi-files/Random_forest"
        
        result = subprocess.run([
            sys.executable, "RP_tmp.py",
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
@app.route("/cleanup")
def cleanup():
    try:
        cleanup_temp_files()
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
    def get_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    local_ip = get_ip()
    
    print("=" * 70)
    print("ECG SERVER")
    print("=" * 70)
    print("\nSelect mode:")
    print("  1. Debug mode (use pre-recorded data)")
    print("  2. Regular mode (record from hardware)")
    print()
    
    while True:
        try:
            choice = input("Enter your choice (1 or 2): ").strip()
            if choice == "1":
                debug_mode = True
                print("\n✓ Debug mode enabled")
                break
            elif choice == "2":
                debug_mode = False
                print("\n✓ Regular mode enabled")
                break
            else:
                print("Invalid choice. Please enter 1 or 2.")
        except (KeyboardInterrupt, EOFError):
            print("\n\nExiting...")
            sys.exit(0)
    
    print("\n" + "=" * 70)
    print(f"Local: http://127.0.0.1:8000")
    print(f"Network: http://{local_ip}:8000")
    print(f"Mode: {'DEBUG' if debug_mode else 'REGULAR'}")
    print("=" * 70 + "\n")
    
    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=8000, threads=4)
    except ImportError:
        app.run(host="0.0.0.0", port=8000, threaded=True, debug=False)
