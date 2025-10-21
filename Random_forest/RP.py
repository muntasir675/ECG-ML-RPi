import pandas as pd
import numpy as np
import joblib
import glob

csv_path = "/home/pi/Desktop/raspi-files/Random_forest/ECGCvdata.csv"

print("="*60)
print("ECG DATA INPUT FORMATTER")
print("="*60)

# Load preprocessing objects
preprocessing_files = glob.glob('/home/pi/Desktop/raspi-files/Random_forest/ecg_preprocessing_*.pkl')
if not preprocessing_files:
    print("❌ Error: Preprocessing files not found!")
    print("Please ensure the model training script has been run first.")
else:
    preprocessing_file = sorted(preprocessing_files)[-1]
    print(f"Loading preprocessing from: {preprocessing_file}")
    preprocessing = joblib.load(preprocessing_file)
    
    label_encoder = preprocessing['label_encoder']
    selected_features = preprocessing['selected_features']
    train_medians = preprocessing['train_medians']
    
    print(f"✅ Loaded preprocessing objects")
    print(f"✅ Classes: {label_encoder.classes_}")
    print(f"   Expected features: {len(selected_features)}")

# Example 1: Format data from a CSV row
def format_from_csv_row(csv_path, row_index=0):
    """
    Load a row from the original CSV and format it for prediction
    
    Parameters:
    - csv_path: Path to the ECG CSV file
    - row_index: Which row to extract (default: 0)
    
    Returns:
    - Formatted DataFrame ready for model prediction
    """
    print(f"\n--- Formatting from CSV row {row_index} ---")
    
    # Load the raw data
    df = pd.read_csv(csv_path)
    print(f"Loaded CSV with shape: {df.shape}")
    
    # Extract the row
    row_data = df.iloc[[row_index]].copy()
    
    # Remove RECORD and ECG_signal columns if present
    cols_to_drop = []
    if 'RECORD' in row_data.columns:
        cols_to_drop.append('RECORD')
    if 'ECG_signal' in row_data.columns:
        actual_label = row_data['ECG_signal'].values[0]
        print(f"Actual label: {actual_label}")
        cols_to_drop.append('ECG_signal')
    
    X_input = row_data.drop(columns=cols_to_drop, errors='ignore')
    
    # Apply preprocessing
    X_filled = X_input.fillna(train_medians)
    X_formatted = X_filled[selected_features]
    
    print(f"✅ Formatted data shape: {X_formatted.shape}")
    return X_formatted

# Example 2: Format data from a dictionary
def format_from_dict(data_dict):
    """
    Format ECG data from a dictionary of features
    
    Parameters:
    - data_dict: Dictionary with feature names as keys and values
    
    Returns:
    - Formatted DataFrame ready for model prediction
    """
    print(f"\n--- Formatting from dictionary ---")
    print(f"Input features: {len(data_dict)}")
    
    # Convert to DataFrame
    df_input = pd.DataFrame([data_dict])
    
    # Fill missing values
    X_filled = df_input.fillna(train_medians)
    
    # Select only the features the model was trained on
    # If some features are missing, they'll be filled with median
    X_formatted = pd.DataFrame()
    for feature in selected_features:
        if feature in X_filled.columns:
            X_formatted[feature] = X_filled[feature]
        else:
            # Use median for missing features
            X_formatted[feature] = train_medians[feature]
            print(f"⚠️  Feature '{feature}' not in input, using median: {train_medians[feature]:.4f}")
    
    print(f"✅ Formatted data shape: {X_formatted.shape}")
    return X_formatted

# Example 3: Format data from a Pandas Series
def format_from_series(series_data):
    """
    Format ECG data from a Pandas Series
    
    Parameters:
    - series_data: Pandas Series with feature values
    
    Returns:
    - Formatted DataFrame ready for model prediction
    """
    print(f"\n--- Formatting from Series ---")
    
    # Convert to DataFrame
    df_input = pd.DataFrame([series_data])
    
    # Remove RECORD and ECG_signal if present
    df_input = df_input.drop(columns=['RECORD', 'ECG_signal'], errors='ignore')
    
    # Fill missing values
    X_filled = df_input.fillna(train_medians)
    
    # Select features
    X_formatted = X_filled[selected_features]
    
    print(f"✅ Formatted data shape: {X_formatted.shape}")
    return X_formatted

# DEMONSTRATION
print("\n" + "="*60)
print("DEMONSTRATION")
print("="*60)

# Demo 1: From CSV
X_test_formatted = format_from_csv_row(csv_path, row_index=908)
print(f"\nFirst 5 features:")
print(X_test_formatted.iloc[0, :5])


# Demo 3: From the original dataframe
df = pd.read_csv(csv_path)
sample_series = df.iloc[10]
X_test_from_series = format_from_series(sample_series)

print("\n" + "="*60)
print("✅ All formatting methods demonstrated!")
print("="*60)
print("\nYou can now use any of these formatted inputs with the model:")
print("  - X_test_formatted")
print("  - X_test_from_dict")
print("  - X_test_from_series")



# Load saved model (preprocessing already loaded in formatter code)
print("\n" + "="*60)
print("LOADING MODEL FOR PREDICTION")
print("="*60)

import joblib
import glob

# Find the most recent model file
model_files = glob.glob('/home/pi/Desktop/raspi-files/Random_forest/ecg_random_forest_model_*.pkl')

if not model_files:
    print("❌ Error: Model file not found!")
else:
    model_file = sorted(model_files)[-1]
    print(f"Loading model from: {model_file}")
    
    # Load model only (preprocessing already loaded)
    loaded_model = joblib.load(model_file)
    
    print(f"✅ Model loaded successfully!")
    
    # Make prediction using ALREADY FORMATTED data from formatter code
    print("\n" + "="*60)
    print("MODEL PREDICTION")
    print("="*60)
    print(X_test_formatted)
    
    # Use X_test_formatted from the formatter code (already preprocessed)
    prediction = loaded_model.predict(X_test_formatted)
    probabilities = loaded_model.predict_proba(X_test_formatted)[0]
    
    predicted_label = label_encoder.inverse_transform(prediction)[0]
    
    print(f"\n{'─'*60}")
    print(f"PREDICTION RESULT")
    print(f"{'─'*60}")
    print(f"Predicted diagnosis: {predicted_label}")
    print(f"Confidence: {max(probabilities):.2%}")
    print(f"\nProbabilities for each class:")
    for class_name, prob in zip(label_encoder.classes_, probabilities):
        bar = '█' * int(prob * 50)

        print(f"  {class_name:20s} {prob:6.2%} {bar}")




