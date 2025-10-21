import subprocess
import sys

def run(cmd, desc):
    print(f"\n[⏳] {desc}...")
    try:
        subprocess.check_call(cmd, shell=True)
        print(f"[✅] {desc} - SUCCESS")
        return True
    except subprocess.CalledProcessError:
        print(f"[❌] {desc} - FAILED")
        return False

def check_pip():
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "--version"], 
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except:
        return False

def install_pkg(pkg):
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
        return True
    except:
        return False

print("\nRaspberry Pi Setup\n")

# System packages
run("sudo apt update", "Updating system")

if not check_pip():
    run("sudo apt install python3-pip -y", "Installing pip")

run("sudo apt install python3-dev build-essential -y", "Installing build tools")
run("sudo apt install libatlas-base-dev libopenblas-dev -y", "Installing performance libraries")
run("sudo apt install python3-serial i2c-tools python3-smbus -y", "Installing I2C/Serial tools")

# Enable interfaces
run("sudo raspi-config nonint do_i2c 0", "Enabling I2C")
run("sudo raspi-config nonint do_serial 0", "Enabling Serial")

# Python packages
packages = ['numpy', 'pandas', 'matplotlib', 'scipy', 'PyWavelets', 'joblib', 'adafruit-circuitpython-ads1x15']

print("\nInstalling Python packages...")

failed = []
for pkg in packages:
    try:
        __import__(pkg.lower().replace('pywavelets', 'pywt').replace('adafruit-circuitpython-ads1x15', 'adafruit_ads1x15'))
        print(f"[✅] {pkg} already installed")
    except ImportError:
        print(f"[⏳] Installing {pkg}...")
        if install_pkg(pkg):
            print(f"[✅] {pkg} installed")
        else:
            print(f"[❌] {pkg} failed")
            failed.append(pkg)

print("\nSetup complete!")
if failed:
    print(f"Failed packages: {', '.join(failed)}")

print("\nReboot required for I2C/Serial: sudo reboot")
