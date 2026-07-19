# ECG-ML-RPi

ECG monitoring and classification system on Raspberry Pi using machine learning.

Reads ECG data from an ADC via the Linux IIO subsystem, extracts features, runs a Random Forest classifier, and serves results through a server.

## Structure

- `src/` — Main application code (recorder, server)
- `models/` — Trained ML models (preprocessing + random forest)
- `data/` — ECG recordings and datasets
- `prototyping/` — Experimental/development scripts
