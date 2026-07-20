import pandas as pd
import numpy as np
import joblib
import glob
import os
import sys
import argparse

def format_from_csv_row(csv_path, row_index, train_medians, selected_features):
    df = pd.read_csv(csv_path)
    row_data = df.iloc[[row_index]].copy()
    cols_to_drop = []
    if 'RECORD' in row_data.columns:
        cols_to_drop.append('RECORD')
    if 'ECG_signal' in row_data.columns:
        actual_label = row_data['ECG_signal'].values[0]
        print(f"Actual label: {actual_label}")
        cols_to_drop.append('ECG_signal')
    X_input = row_data.drop(columns=cols_to_drop, errors='ignore')
    X_filled = X_input.fillna(train_medians)
    X_formatted = X_filled[selected_features]
    return X_formatted

def format_from_series(series_data, train_medians, selected_features):
    df_input = pd.DataFrame([series_data])
    df_input = df_input.drop(columns=['RECORD', 'ECG_signal'], errors='ignore')
    X_filled = df_input.fillna(train_medians)
    X_formatted = X_filled[selected_features]
    return X_formatted

def load_preprocessing(model_dir):
    preprocessing_files = glob.glob(os.path.join(model_dir, 'ecg_preprocessing_*.pkl'))
    if not preprocessing_files:
        print("Error: Preprocessing files not found!")
        sys.exit(1)
    preprocessing_file = sorted(preprocessing_files)[-1]
    print(f"Loading preprocessing from: {preprocessing_file}")
    preprocessing = joblib.load(preprocessing_file)
    return preprocessing

def load_model(model_dir):
    model_files = glob.glob(os.path.join(model_dir, 'ecg_random_forest_model_*.pkl'))
    if not model_files:
        print("Error: Model file not found!")
        sys.exit(1)
    model_file = sorted(model_files)[-1]
    print(f"Loading model from: {model_file}")
    return joblib.load(model_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='ECG Diagnosis Prediction')
    parser.add_argument('--input', required=True, help='Input features CSV path')
    parser.add_argument('--output', required=True, help='Output diagnosis CSV path')
    parser.add_argument('--model-dir', required=True, help='Directory with preprocessing and model .pkl files')
    args = parser.parse_args()

    preprocessing = load_preprocessing(args.model_dir)
    label_encoder = preprocessing['label_encoder']
    selected_features = preprocessing['selected_features']
    train_medians = preprocessing['train_medians']

    loaded_model = load_model(args.model_dir)

    df_features = pd.read_csv(args.input)
    X_formatted = format_from_csv_row(args.input, 0, train_medians, selected_features)

    prediction = loaded_model.predict(X_formatted)
    probabilities = loaded_model.predict_proba(X_formatted)[0]
    predicted_label = label_encoder.inverse_transform(prediction)[0]

    result_df = pd.DataFrame([{
        'diagnosis': predicted_label,
        'confidence': max(probabilities)
    }])
    for class_name, prob in zip(label_encoder.classes_, probabilities):
        result_df[f'prob_{class_name}'] = prob

    result_df.to_csv(args.output, index=False)
    print(f"Diagnosis saved to: {args.output}")
