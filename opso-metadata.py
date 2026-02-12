"""
Convert Open Soundscape JSON metadata to a standardized format.

How to create at input file:
    events_dict = {"localized_events": [e.to_dict() for e in localized_events]}
    with open(out_file, "w+") as f:
        json.dump(events_dict, f)

How to run the script:
    python opso-metadata.py <input_file>


"""


import pandas as pd
import json
import os
import argparse
from pprint import pprint as pp


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("json_file", type=str,  help = 'Path to OpenSoundscape generated JSON file.')
    parser.add_argument("-o", "--out", type=str, default=None, help = "Path to output file.")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", default=False, help = "Don't export outputs.")
    parser.add_argument("--prefix", type=str, default=None, help = "Dataset prefix.")
    
    return parser.parse_args()

# prefix = args.prefix
# prefix = 'cmarsh'

# #-------------------------------------------------------------------------------------
if __name__ == "__main__":
    args = parse_args()
    
    prefix = args.prefix
    
    # Input file -----------------------------------------------------------------------
    json_file = args.json_file
    # json_file = '/Users/lviotti/Library/CloudStorage/Dropbox/Work/Kitzes/projects/data-loca/localized_events.json'

    with open(json_file, 'r') as f:
        data = json.load(f)

    # pp(data)

    event_list = data['localized_events']

    df_list = []
    for event in event_list:
        # pp(event)
        
        # Round numeric columns to 3 decimal places
        event['tdoas'] = [round(x, 7) for x in event['tdoas']]
        event['distance_residuals'] = [round(x, 3) for x in event['distance_residuals']]
        
        # Convert to DataFrame
        df_e = pd.DataFrame([event])
        df_list.append(df_e)

    df = pd.concat(df_list)

    # Create ID -----------------------------------------------------------------------
    df = df.reset_index(drop=True)

    df["parsed_timestamp"] = (
        df["start_timestamp"]
            .astype(str)
            .str.replace(r"[^\d]", "", regex=True)  # keep only digits
            .str[:-8]                               # remove last two digits
    )

    if prefix is not None:
        df['event_id'] = prefix + '_' + df["parsed_timestamp"] + '_' + df.index.astype(str).str.zfill(3)
    else:
        df['event_id'] = df["parsed_timestamp"] + '_' + df.index.astype(str).str.zfill(3)


    # Cosmetics -----------------------------------------------------------------------
    df = df.rename(columns={
        'location_estimate': 'position',
        'class_name': 'label',
        'receiver_start_time_offsets': 'file_start_time_offsets',
        'receiver_files': 'file_ids',})

    columns_to_keep = [
        'event_id', 
        'label', 
        'start_timestamp', 
        'duration', 
        'position', 
        'file_ids', 
        'file_start_time_offsets',
        'tdoas', 
        'distance_residuals' ]
    
    # Output file ---------------------------------------------------------------------
    if prefix is not None:
        output_filename = f'{prefix}_localized_events.csv'
    else:
        output_filename = 'localized_events.csv'
    
    if args.out is not None:
        output_filename = os.path.join(args.out, output_filename)
    
    if not args.dry_run:
        df[columns_to_keep].to_csv(output_filename, index=False)
    else:
        print(f'Dry run. Would have exported to {output_filename}')



