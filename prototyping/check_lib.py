packages = [
    'numpy', 'pandas', 'matplotlib', 'scipy', 'pywt', 'joblib', 'adafruit_ads1x15'
]
for pkg in packages:
    try:
        __import__(pkg)
        print(f"[✅] {pkg} is installed")
    except ImportError:
        print(f"[❌] {pkg} is NOT installed")
