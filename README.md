# ECG-ML-RPi

ECG monitoring and ML classification on Raspberry Pi.
Reads ADS1293 ADC data via the Linux IIO subsystem, extracts features,
runs a Random Forest classifier, and serves results.

## Structure
- `src/recorder.cpp` — IIO ADC reader + feature extraction
- `src/server/` — HTTP server for live results
- `models/` — Preprocessing pipeline + trained Random Forest .pkl
- `data/recordings/` — 13 CSV ECG recordings
- `prototyping/` — Experimental Python scripts (extraction, RF training, data reader)

## Usage
1. Build recorder: `g++ -O3 src/recorder.cpp -o recorder -liio`
2. Run recorder to capture ECG data
3. Load model in `models/` and classify
