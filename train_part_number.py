import os
import json
import pandas as pd

VALVE_CSV_FILE = r"D:\C102641-Data\copy_folder\Valve_Final_Inspection\Valve_Details.csv"
MASTER_FILE = r"D:\C102641-Data\copy_folder\Valve_Final_Inspection\trained_data\valve_master.json"
os.makedirs(os.path.dirname(MASTER_FILE), exist_ok=True)

try:
    valve_data = pd.read_csv(VALVE_CSV_FILE)
    print("CSV Loaded successfully!")
except FileNotFoundError:
    print(f"Error: CSV file not found at {VALVE_CSV_FILE}")
    exit(1)
print("Preview of CSV data:")
print(valve_data.head())

master_data = {"valves": valve_data.to_dict(orient="records")}

try:
    with open(MASTER_FILE, "w") as f:
        json.dump(master_data, f, indent=4)
    print(f"Master JSON saved successfully at: {MASTER_FILE}")
except Exception as e:
    print(f"Error saving JSON: {e}")
    exit(1)

try:
    with open(MASTER_FILE, "r") as f:
        loaded_data = json.load(f)
    print("JSON loaded successfully. Number of valves:", len(loaded_data["valves"]))
except Exception as e:
    print(f"Error loading JSON: {e}")
