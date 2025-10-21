"""
ECG Feature Extractor for Raspberry Pi
Extracts 54 features from ECG signals for heart disease classification
"""

import numpy as np
import pandas as pd
from scipy import signal
from scipy.signal import find_peaks, butter, filtfilt
from scipy.spatial.distance import euclidean
import pywt
import warnings
warnings.filterwarnings('ignore')


DATASET_PATH = '/home/pi/Desktop/raspi-files/Extract/ecg_signal_rows.csv'

SAMPLE_INDEX = 13
SAMPLING_RATE = 100
GAIN = 1.0

LEAD_COLUMN = 'lead_1'

# Output CSV path
OUTPUT_CSV_PATH = '/home/pi/Desktop/raspi-files/Random_forest/ecg_features_output.csv'


class ECGFeatureExtractor:
    def __init__(self, sampling_rate=100):
        self.fs = sampling_rate
        self.features = {}

    def bandpass_filter(self, signal_data, lowcut=0.5, highcut=40):
        """Apply bandpass filter to ECG signal"""
        nyquist = 0.5 * self.fs
        low = lowcut / nyquist
        high = highcut / nyquist
        b, a = butter(4, [low, high], btype='band')
        return filtfilt(b, a, signal_data)

    def normalize_signal(self, signal_data, gain=1.0):
        """Normalize ECG signal with specified gain"""
        normalized = (signal_data - np.mean(signal_data)) / np.std(signal_data)
        return normalized * gain

    def detect_r_peaks(self, ecg_signal):
        """Detect R peaks in ECG signal"""
        peaks, properties = find_peaks(ecg_signal,
                                     height=np.std(ecg_signal) * 0.5,
                                     distance=int(0.4 * self.fs),
                                     prominence=np.std(ecg_signal) * 0.3)
        return peaks

    def detect_ecg_waves(self, ecg_signal, r_peaks):
        """Detect P, Q, S, T waves and their boundaries"""
        waves = {}

        for i, r_peak in enumerate(r_peaks):
            wave_dict = {'R': r_peak}

            search_window = int(0.2 * self.fs)
            qrs_window = int(0.08 * self.fs)

            q_start = max(0, r_peak - qrs_window)
            q_region = ecg_signal[q_start:r_peak]
            if len(q_region) > 0:
                q_idx = np.argmin(q_region)
                wave_dict['Q'] = q_start + q_idx

            s_end = min(len(ecg_signal), r_peak + qrs_window)
            s_region = ecg_signal[r_peak:s_end]
            if len(s_region) > 0:
                s_idx = np.argmin(s_region)
                wave_dict['S'] = r_peak + s_idx

            if 'Q' in wave_dict:
                p_start = max(0, wave_dict['Q'] - search_window)
                p_region = ecg_signal[p_start:wave_dict['Q']]
                if len(p_region) > 0:
                    p_peaks, _ = find_peaks(p_region, height=np.std(p_region) * 0.1)
                    if len(p_peaks) > 0:
                        wave_dict['P'] = p_start + p_peaks[-1]
                        p_on_region = ecg_signal[p_start:wave_dict['P']]
                        wave_dict['P_on'] = p_start + np.argmin(np.abs(p_on_region - np.mean(p_on_region)))

            if 'S' in wave_dict:
                t_start = wave_dict['S']
                t_end = min(len(ecg_signal), r_peak + int(0.4 * self.fs))
                t_region = ecg_signal[t_start:t_end]
                if len(t_region) > 0:
                    t_peaks, _ = find_peaks(t_region, height=np.std(t_region) * 0.1)
                    if len(t_peaks) > 0:
                        wave_dict['T'] = t_start + t_peaks[0]
                        t_off_region = ecg_signal[wave_dict['T']:t_end]
                        if len(t_off_region) > 0:
                            wave_dict['T_off'] = wave_dict['T'] + np.argmin(np.abs(t_off_region - np.mean(t_off_region)))

            waves[i] = wave_dict

        return waves

    def calculate_distances(self, waves, ecg_signal):
        """Calculate Euclidean distances between wave points"""
        distances = {}

        for beat_idx, wave_dict in waves.items():
            beat_distances = {}
            points = {}

            for wave_type, idx in wave_dict.items():
                if idx < len(ecg_signal):
                    points[wave_type] = (idx, ecg_signal[idx])

            wave_pairs = [
                ('P', 'Q'), ('P_on', 'Q'), ('P', 'R'), ('P_on', 'R'),
                ('P', 'S'), ('P_on', 'S'), ('P', 'T'), ('P_on', 'T'),
                ('P', 'T_off'), ('Q', 'R'), ('Q', 'S'), ('Q', 'T'),
                ('Q', 'T_off'), ('R', 'S'), ('R', 'T'), ('R', 'T_off'),
                ('S', 'T'), ('S', 'T_off'), ('P_on', 'T_off')
            ]

            for p1, p2 in wave_pairs:
                if p1 in points and p2 in points:
                    dist = euclidean(points[p1], points[p2])
                    beat_distances[f"{p1}{p2}dis"] = dist

            distances[beat_idx] = beat_distances

        return distances

    def calculate_angles(self, waves, ecg_signal):
        """Calculate angles between three consecutive points"""
        angles = {}

        for beat_idx, wave_dict in waves.items():
            beat_angles = {}
            points = {}

            for wave_type, idx in wave_dict.items():
                if idx < len(ecg_signal):
                    points[wave_type] = np.array([idx, ecg_signal[idx]])

            angle_triplets = [
                ('P_on', 'P', 'Q'), ('P', 'Q', 'R'), ('Q', 'R', 'S'),
                ('R', 'S', 'T'), ('S', 'T', 'T_off')
            ]

            for p1, p2, p3 in angle_triplets:
                if all(p in points for p in [p1, p2, p3]):
                    v1 = points[p1] - points[p2]
                    v2 = points[p3] - points[p2]

                    cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
                    cos_angle = np.clip(cos_angle, -1, 1)
                    angle = np.arccos(cos_angle) * 180 / np.pi

                    angle_name = f"{p1}{p2}{p3}ang".replace('_', '')
                    beat_angles[angle_name] = angle

            angles[beat_idx] = beat_angles

        return angles

    def calculate_slopes(self, waves, ecg_signal):
        """Calculate slopes between wave points"""
        slopes = {}

        for beat_idx, wave_dict in waves.items():
            beat_slopes = {}
            slope_pairs = [('P', 'Q'), ('Q', 'R'), ('R', 'S'), ('S', 'T')]

            for p1, p2 in slope_pairs:
                if p1 in wave_dict and p2 in wave_dict:
                    x1, x2 = wave_dict[p1], wave_dict[p2]
                    y1, y2 = ecg_signal[x1], ecg_signal[x2]

                    if x2 != x1:
                        slope = (y2 - y1) / (x2 - x1)
                        beat_slopes[f"{p1}{p2}slope"] = slope

            slopes[beat_idx] = beat_slopes

        return slopes

    def calculate_qrs_features(self, waves, ecg_signal):
        """Calculate QRS area and perimeter"""
        qrs_features = {}

        for beat_idx, wave_dict in waves.items():
            if all(k in wave_dict for k in ['Q', 'R', 'S']):
                q_idx = wave_dict['Q']
                r_idx = wave_dict['R']
                s_idx = wave_dict['S']

                x_coords = [q_idx, r_idx, s_idx]
                y_coords = [ecg_signal[q_idx], ecg_signal[r_idx], ecg_signal[s_idx]]

                area = 0.5 * abs(sum(x_coords[i] * y_coords[(i + 1) % 3] -
                                   x_coords[(i + 1) % 3] * y_coords[i] for i in range(3)))

                qr_dist = euclidean([q_idx, ecg_signal[q_idx]], [r_idx, ecg_signal[r_idx]])
                rs_dist = euclidean([r_idx, ecg_signal[r_idx]], [s_idx, ecg_signal[s_idx]])
                qs_dist = euclidean([q_idx, ecg_signal[q_idx]], [s_idx, ecg_signal[s_idx]])
                perimeter = qr_dist + rs_dist + qs_dist

                qrs_features[beat_idx] = {
                    'QRSarea': area,
                    'QRSperi': perimeter
                }

        return qrs_features

    def extract_features(self, ecg_signal, gain=1.0):
        """Extract all 54 ECG features"""
        filtered_signal = self.bandpass_filter(ecg_signal)
        normalized_signal = self.normalize_signal(filtered_signal, gain)

        r_peaks = self.detect_r_peaks(normalized_signal)

        if len(r_peaks) < 2:
            return self._get_default_features()

        waves = self.detect_ecg_waves(normalized_signal, r_peaks)
        rr_intervals = np.diff(r_peaks) / self.fs * 1000

        features = {}
        features['hbpermin'] = 60000 / np.mean(rr_intervals) if len(rr_intervals) > 0 else 0

        segment_features = self._calculate_segment_lengths(waves, normalized_signal)
        features.update(segment_features)

        features['RRmean'] = np.mean(rr_intervals) if len(rr_intervals) > 0 else 0

        p_peaks = [waves[i]['P'] for i in waves if 'P' in waves[i]]
        if len(p_peaks) > 1:
            pp_intervals = np.diff(p_peaks) / self.fs * 1000
            features['PPmean'] = np.mean(pp_intervals)
        else:
            features['PPmean'] = 0

        distances = self.calculate_distances(waves, normalized_signal)
        distance_features = self._aggregate_features(distances)
        features.update(distance_features)

        angles = self.calculate_angles(waves, normalized_signal)
        angle_features = self._aggregate_features(angles)
        features.update(angle_features)

        features['RRTot'] = len(r_peaks)
        features['NNTot'] = len(rr_intervals)

        hrv_features = self._calculate_hrv_features(rr_intervals)
        features.update(hrv_features)

        qrs_features = self.calculate_qrs_features(waves, normalized_signal)
        qrs_aggregated = self._aggregate_features(qrs_features)
        features.update(qrs_aggregated)

        slopes = self.calculate_slopes(waves, normalized_signal)
        slope_features = self._aggregate_features(slopes)
        features.update(slope_features)

        nn50_features = self._calculate_nn50_features(rr_intervals)
        features.update(nn50_features)

        duration_features = self._calculate_duration_features(waves)
        features.update(duration_features)

        return features

    def _calculate_segment_lengths(self, waves, ecg_signal):
        """Calculate segment lengths between wave points (in SECONDS)"""
        segments = {}
        all_segments = {
            'Pseg': [], 'PQseg': [], 'QRSseg': [], 'QRseg': [], 'QTseg': [],
            'RSseg': [], 'STseg': [], 'Tseg': [], 'PTseg': [], 'ECGseg': []
        }

        for beat_idx, wave_dict in waves.items():
            if 'P_on' in wave_dict and 'P' in wave_dict:
                p_len = abs(wave_dict['P'] - wave_dict['P_on']) / self.fs
                all_segments['Pseg'].append(p_len)

            if 'P' in wave_dict and 'Q' in wave_dict:
                pq_len = abs(wave_dict['Q'] - wave_dict['P']) / self.fs
                all_segments['PQseg'].append(pq_len)

            if all(k in wave_dict for k in ['Q', 'S']):
                qrs_len = abs(wave_dict['S'] - wave_dict['Q']) / self.fs
                all_segments['QRSseg'].append(qrs_len)

            if 'Q' in wave_dict and 'R' in wave_dict:
                qr_len = abs(wave_dict['R'] - wave_dict['Q']) / self.fs
                all_segments['QRseg'].append(qr_len)

            if 'Q' in wave_dict and 'T' in wave_dict:
                qt_len = abs(wave_dict['T'] - wave_dict['Q']) / self.fs
                all_segments['QTseg'].append(qt_len)

            if 'R' in wave_dict and 'S' in wave_dict:
                rs_len = abs(wave_dict['S'] - wave_dict['R']) / self.fs
                all_segments['RSseg'].append(rs_len)

            if 'S' in wave_dict and 'T' in wave_dict:
                st_len = abs(wave_dict['T'] - wave_dict['S']) / self.fs
                all_segments['STseg'].append(st_len)

            if 'T' in wave_dict and 'T_off' in wave_dict:
                t_len = abs(wave_dict['T_off'] - wave_dict['T']) / self.fs
                all_segments['Tseg'].append(t_len)

            if 'P' in wave_dict and 'T' in wave_dict:
                pt_len = abs(wave_dict['T'] - wave_dict['P']) / self.fs
                all_segments['PTseg'].append(pt_len)

            if 'P_on' in wave_dict and 'T_off' in wave_dict:
                ecg_len = abs(wave_dict['T_off'] - wave_dict['P_on']) / self.fs
                all_segments['ECGseg'].append(ecg_len)

        for seg_name, values in all_segments.items():
            segments[seg_name] = np.mean(values) if len(values) > 0 else 0

        return segments

    def _calculate_duration_features(self, waves):
        """Calculate QR to QS and RS to QS durations (in SECONDS)"""
        durations = {'QRtoQSdur': [], 'RStoQSdur': []}

        for beat_idx, wave_dict in waves.items():
            if all(k in wave_dict for k in ['Q', 'R', 'S']):
                qr_dur = abs(wave_dict['R'] - wave_dict['Q']) / self.fs
                qs_dur = abs(wave_dict['S'] - wave_dict['Q']) / self.fs
                durations['QRtoQSdur'].append(qr_dur / qs_dur if qs_dur != 0 else 0)

                rs_dur = abs(wave_dict['S'] - wave_dict['R']) / self.fs
                durations['RStoQSdur'].append(rs_dur / qs_dur if qs_dur != 0 else 0)

        return {
            'QRtoQSdur': np.mean(durations['QRtoQSdur']) if len(durations['QRtoQSdur']) > 0 else 0,
            'RStoQSdur': np.mean(durations['RStoQSdur']) if len(durations['RStoQSdur']) > 0 else 0
        }

    def _calculate_hrv_features(self, rr_intervals):
        """Calculate HRV (Heart Rate Variability) features"""
        if len(rr_intervals) < 2:
            return {'SDRR': 0, 'IBIM': 0, 'IBISD': 0, 'SDSD': 0, 'RMSSD': 0}

        sdrr = np.std(rr_intervals)
        ibim = np.mean(rr_intervals)
        ibisd = np.std(rr_intervals)

        diff_rr = np.diff(rr_intervals)
        sdsd = np.std(diff_rr) if len(diff_rr) > 0 else 0
        rmssd = np.sqrt(np.mean(diff_rr**2)) if len(diff_rr) > 0 else 0

        return {
            'SDRR': sdrr,
            'IBIM': ibim,
            'IBISD': ibisd,
            'SDSD': sdsd,
            'RMSSD': rmssd
        }

    def _calculate_nn50_features(self, rr_intervals):
        """Calculate NN50 and pNN50 features"""
        if len(rr_intervals) < 2:
            return {'NN50': 0, 'pNN50': 0}

        diff_rr = np.abs(np.diff(rr_intervals))
        nn50 = np.sum(diff_rr > 50)
        pnn50 = (nn50 / len(diff_rr)) * 100 if len(diff_rr) > 0 else 0

        return {'NN50': nn50, 'pNN50': pnn50}

    def _aggregate_features(self, feature_dict):
        aggregated = {}

        if not feature_dict:
            return aggregated

        all_features = set()
        for beat_features in feature_dict.values():
            all_features.update(beat_features.keys())

        for feature_name in all_features:
            values = [beat_features.get(feature_name, 0) for beat_features in feature_dict.values()]
            values = [v for v in values if v is not None and not np.isnan(v)]
            aggregated[feature_name] = np.mean(values) if len(values) > 0 else 0

        return aggregated

    def _get_default_features(self):
        feature_names = [
            'hbpermin', 'Pseg', 'PQseg', 'QRSseg', 'QRseg', 'QTseg', 'RSseg', 'STseg',
            'Tseg', 'PTseg', 'ECGseg', 'QRtoQSdur', 'RStoQSdur', 'RRmean', 'PPmean',
            'PQdis', 'PonQdis', 'PRdis', 'PonRdis', 'PSdis', 'PonSdis', 'PTdis',
            'PonTdis', 'PToffdis', 'QRdis', 'QSdis', 'QTdis', 'QToffdis', 'RSdis',
            'RTdis', 'RToffdis', 'STdis', 'SToffdis', 'PonToffdis', 'PonPQang',
            'PQRang', 'QRSang', 'RSTang', 'STToffang', 'RRTot', 'NNTot', 'SDRR',
            'IBIM', 'IBISD', 'SDSD', 'RMSSD', 'QRSarea', 'QRSperi', 'PQslope',
            'QRslope', 'RSslope', 'STslope', 'NN50', 'pNN50'
        ]
        return {name: 0 for name in feature_names}


def load_ecg_data(csv_path, sample_index, lead_column='lead_1'):
    """Load a single flattened ECG signal from CSV where each row is one ECG"""
    print(f"Loading data from: {csv_path}")
    print(f"Loading only sample #{sample_index}...")

    df = pd.read_csv(csv_path)

    if sample_index >= len(df):
        raise ValueError(f"Sample index {sample_index} out of range. Available: 0-{len(df)-1}")

    row = df.iloc[sample_index]

    target_id = row.iloc[0]
    signal_data = row.iloc[1:].tolist()

    print(f"Loaded ECG ID: {target_id} with {len(signal_data)} samples")
    return signal_data, target_id


def save_features_to_csv(features, output_path, record_id=None):
    """Save extracted features to CSV in the specified format"""
    if record_id is not None:
        features['RECORD'] = record_id  # rename from ecg_id to RECORD

    # exact column order you want
    column_order = [
        'RECORD', 'hbpermin', 'Pseg', 'PQseg', 'QRSseg', 'QRseg', 'QTseg', 'RSseg', 'STseg', 'Tseg',
        'PTseg', 'ECGseg', 'QRtoQSdur', 'RStoQSdur', 'RRmean', 'PPmean', 'PQdis', 'PonQdis', 'PRdis',
        'PonRdis', 'PSdis', 'PonSdis', 'PTdis', 'PonTdis', 'PToffdis', 'QRdis', 'QSdis', 'QTdis',
        'QToffdis', 'RSdis', 'RTdis', 'RToffdis', 'STdis', 'SToffdis', 'PonToffdis', 'PonPQang',
        'PQRang', 'QRSang', 'RSTang', 'STToffang', 'RRTot', 'NNTot', 'SDRR', 'IBIM', 'IBISD', 'SDSD',
        'RMSSD', 'QRSarea', 'QRSperi', 'PQslope', 'QRslope', 'RSslope', 'STslope', 'NN50', 'pNN50'
    ]

    # fill missing columns with 0
    for col in column_order:
        if col not in features:
            features[col] = 0

    df = pd.DataFrame([features], columns=column_order)
    df.to_csv(output_path, index=False, float_format='%.8f')
    print(f"\nFeatures saved to: {output_path}")
    print(f"CSV shape: {df.shape}")
    return df



def process_ecg_dataset(ecg_data, sampling_rate=100, gain=1.0):
    """Process entire ECG dataset and extract features"""
    extractor = ECGFeatureExtractor(sampling_rate)

    if isinstance(ecg_data, pd.DataFrame):
        features_list = []
        for idx, row in ecg_data.iterrows():
            if isinstance(row.iloc[0], (list, tuple, np.ndarray)):
                signal = np.array(row.iloc[0])
            else:
                signal = row.values

            features = extractor.extract_features(signal, gain)
            features['sample_id'] = idx
            features_list.append(features)

        return pd.DataFrame(features_list)

    elif isinstance(ecg_data, np.ndarray):
        if ecg_data.ndim == 1:
            features = extractor.extract_features(ecg_data, gain)
            return pd.DataFrame([features])
        else:
            features_list = []
            for i, signal in enumerate(ecg_data):
                features = extractor.extract_features(signal, gain)
                features['sample_id'] = i
                features_list.append(features)

            return pd.DataFrame(features_list)

    else:
        raise ValueError("ecg_data must be numpy array or pandas DataFrame")


if __name__ == "__main__":
    print("=" * 70)
    print("ECG FEATURE EXTRACTOR - RASPBERRY PI")
    print("=" * 70)

    ecg_signal, ecg_id = load_ecg_data(DATASET_PATH, SAMPLE_INDEX, LEAD_COLUMN)

    print(f"\nAnalyzing ECG ID: {ecg_id}")
    print(f"Signal length: {len(ecg_signal)} samples")
    print(f"Duration: {len(ecg_signal) / SAMPLING_RATE:.2f} seconds")

    print("\nExtracting features...")
    extractor = ECGFeatureExtractor(sampling_rate=SAMPLING_RATE)
    features = extractor.extract_features(ecg_signal, gain=GAIN)

    print("\n" + "=" * 70)
    print("EXTRACTED ECG FEATURES")
    print("=" * 70)

    max_name_length = max(len(name) for name in features.keys())

    for feature_name, value in features.items():
        print(f"{feature_name:<{max_name_length}} : {value:>12.4f}")

    # Save features to CSV
    features_df = save_features_to_csv(features, OUTPUT_CSV_PATH, record_id=1)  # 1, 2, ... for each record

    print("\n" + "=" * 70)
    print(f"Feature DataFrame shape : {features_df.shape}")
    print(f"Total features extracted: {len(features)}")
    print("=" * 70)
