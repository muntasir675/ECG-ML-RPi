# ECG-ML-RPi

ECG monitoring and ML classification on Raspberry Pi.
Reads ADS1015 ADC data via the Linux IIO subsystem, extracts features,
runs a Random Forest classifier, and serves results via Flask.

## Structure
- `src/recorder.py` — IIO ADC reader
- `src/server.py` — Flask HTTP server for live results
- `src/Models/` — Preprocessing pipeline + trained Random Forest .pkl
- `prototyping/` — Experimental Python scripts (extraction, RF training, data reader)

## Usage
Run the server on the Pi and access it via browser. See `src/server.py` for API routes.
