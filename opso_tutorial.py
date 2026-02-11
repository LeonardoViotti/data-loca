"""
Run OpenSoundscape acoustic localization tutorial steps and export localized events to JSON.
https://opensoundscape.org/en/latest/tutorials/acoustic_localization.html

python -i  opso_tutorial.py

"""
import argparse
import json
import os
import subprocess
from datetime import datetime, timedelta

import pandas as pd
import pytz
from opensoundscape.localization import SynchronizedRecorderArray


def json_serial(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "tolist"):
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


DATA_DIR = "tutorial_data"

# ----------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--out", type=str, default="localized_events.json", help="Output JSON file.")
    args = parser.parse_args()
    out_file = args.out

    os.makedirs(DATA_DIR, exist_ok=True)
    cwd = os.getcwd()

    # Download example files into tutorial_data
    subprocess.run(
        [
            "curl",
            "https://drive.google.com/uc?export=download&id=1M4yKM8obqiY0FU2qEriINBDSWtQGqN8E",
            "-L",
            "-o",
            "localization_files.tar",
        ],
        check=True,
        cwd=DATA_DIR,
    )
    subprocess.run(["tar", "-xzf", "localization_files.tar"], check=True, cwd=DATA_DIR)
    subprocess.run(["rm", "localization_files.tar"], check=True, cwd=DATA_DIR)

    os.chdir(DATA_DIR)
    try:
        # Read receiver coordinates
        aru_coords = pd.read_csv("aru_coords.csv", index_col=0)
        array = SynchronizedRecorderArray(aru_coords)

        # Load detections
        detections = pd.read_csv("detections.csv")
        local_timestamp = datetime(2022, 2, 7, 20, 0, 0)
        local_timezone = pytz.timezone("US/Eastern")
        detections["start_timestamp"] = [
            local_timezone.localize(local_timestamp) + timedelta(seconds=s)
            for s in detections["start_time"]
        ]
        detections = detections.set_index(["file", "start_time", "end_time", "start_timestamp"])

        # Localize
        position_estimates = array.localize_detections(
            detections, min_n_receivers=4, max_receiver_dist=100
        )

        # Filter by residual RMS < 5m
        localized_events = [e for e in position_estimates if e.residual_rms < 5]
    finally:
        os.chdir(cwd)

    # Export JSON (to original cwd)
    events_dict = {"localized_events": [e.to_dict() for e in localized_events]}
    with open(out_file, "w") as f:
        json.dump(events_dict, f, default=json_serial, indent=2)
