try:
    print(f"Recording ECG ID {ecg_id}...")
    for _ in range(num_samples):
        try:
            voltage = round(chan.voltage, 3)
            buffer.append(voltage)
            print(f"Voltage: {voltage} V", end='\r')
        except Exception as e:
            print(f"\nI2C read error: {e}")
            buffer.append(None)  # placeholder for failed read
        time.sleep(sampling_delay)

    row = [ecg_id] + buffer
    writer.writerow(row)
    print(f"\nDone! Saved ECG ID {ecg_id} to {csv_file}")

except KeyboardInterrupt:
    print("\nRecording stopped by user")
except Exception as e:
    print(f"\nUnexpected error: {e}")

