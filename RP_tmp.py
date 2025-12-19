import pandas as pd
import numpy as np
import joblib
import glob
import argparse
import sys

def diagnose_ecg(features_csv, output_csv, model_dir):
    try:
        # Load preprocessing objects
        preprocessing_files = glob.glob(f'ecg_preprocessing_*.pkl')
        if not preprocessing_files:
            raise Exception("Preprocessing files not found")
        
        preprocessing_file = sorted(preprocessing_files)[-1]
        preprocessing = joblib.load(preprocessing_file)
        
        label_encoder = preprocessing['label_encoder']
        selected_features = preprocessing['selected_features']
        train_medians = preprocessing['train_medians']
        
        # Load model
        model_files = glob.glob(f'ecg_random_forest_model_*.pkl')
        if not model_files:
            raise Exception("Model file not found")
        
        model_file = sorted(model_files)[-1]
        loaded_model = joblib.load(model_file)
        
        # Load features
        df = pd.read_csv(features_csv)
        df_input = df.drop(columns=['RECORD', 'ECG_signal'], errors='ignore')
        
        # Fill missing values
        X_filled = df_input.fillna(train_medians)
        
        # Select features
        X_formatted = pd.DataFrame()
        for feature in selected_features:
            if feature in X_filled.columns:
                X_formatted[feature] = X_filled[feature]
            else:
                X_formatted[feature] = train_medians[feature]
        
        # Predict
        probabilities = loaded_model.predict_proba(X_formatted)[0]
        percentages = probabilities * 100
        
        # Save output
        output_df = pd.DataFrame([percentages], columns=label_encoder.classes_)
        output_df.to_csv(output_csv, index=False, float_format='%.2f')
        
        # Print result
        top_idx = np.argmax(probabilities)
        print(f"Diagnosis: {label_encoder.classes_[top_idx]} ({percentages[top_idx]:.1f}%)")
        
        return True
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='ECG Diagnosis')
    parser.add_argument('--input', required=True, help='Input features CSV')
    parser.add_argument('--output', required=True, help='Output diagnosis CSV')
    parser.add_argument('--model-dir', default='/home/pi/Desktop/raspi-files/Random_forest', 
                       help='Model directory')
    
    args = parser.parse_args()
    
    if not diagnose_ecg(args.input, args.output, args.model_dir):
        sys.exit(1)
