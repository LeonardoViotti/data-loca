"""
Convert Open Soundscape JSON metadata to a standardized format.

How to create at input file:
    events_dict = {"localized_events": [e.to_dict() for e in localized_events]}
    with open(out_file, "w+") as f:
        json.dump(events_dict, f)

How to run the script:
    python opso-metadata.py <input_file.json>


"""


import pandas as pd
import json
import os
import glob
import argparse
from pprint import pprint as pp


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("json_file", type=str,  help = 'Path to OpenSoundscape generated JSON file with localized events, or a folder containing several.')
    parser.add_argument("-o", "--out", type=str, default=None, help = "Path to output file.")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", default=False, help = "Don't export outputs.")
    parser.add_argument("--prefix", type=str, default=None, help = "Dataset prefix.")
    parser.add_argument("--create-clips", dest="create_clips", action="store_true", default=False, help = "Extract per-event audio clips into audio/ and write localization_metadata/ tables.")

    return parser.parse_args()

# prefix = args.prefix
# prefix = 'cmarsh'

# #-------------------------------------------------------------------------------------
if __name__ == "__main__":
    args = parse_args()
    
    prefix = args.prefix
    
    # Input file -----------------------------------------------------------------------
    json_file = args.json_file

    if os.path.isdir(json_file):
        json_files = sorted(glob.glob(os.path.join(json_file, '*.json')))
    else:
        json_files = [json_file]

    event_list = []
    for jf in json_files:
        with open(jf, 'r') as f:
            data = json.load(f)
        event_list.extend(data['localized_events'])

    df_list = []
    for event in event_list:
        # pp(event)
        
        # Round numeric columns 
        event['tdoas'] = [round(x, 7) for x in event['tdoas']]
        event['distance_residuals'] = [round(x, 3) for x in event['distance_residuals']]
        event['receiver_start_time_offsets'] = [round(x, 3) for x in event['receiver_start_time_offsets']]
         
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
        'class_name': 'label',
        'receiver_start_time_offsets': 'file_start_time_offsets',
        'receiver_files': 'file_ids',})
        
    df['x'] = [p[0] for p in df['location_estimate']]
    df['y'] = [p[1] for p in df['location_estimate']]
    df['z'] = [p[2] if len(p) > 2 else None for p in df['location_estimate']]

    # Create clips and localization_metadata tables -----------------------------------
    if args.create_clips:
        from opensoundscape import Audio

        out_dir = args.out if args.out is not None else '.'
        if not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        
        audio_dir = os.path.join(out_dir, 'audio')
        metadata_dir = os.path.join(out_dir, 'localization_metadata')
        if not args.dry_run:
            os.makedirs(audio_dir, exist_ok=True)
            os.makedirs(metadata_dir, exist_ok=True)

        point_ids = {}
        point_rows = []
        audio_rows = []
        clip_ids = set()
        new_file_ids = []
        new_offsets = []

        for _, row in df.iterrows():
            row_file_ids = []
            row_offsets = []
            for orig_path, loc, offset in zip(row['file_ids'], row['receiver_locations'], row['file_start_time_offsets']):
                loc_key = tuple(round(v, 6) for v in loc)
                if loc_key not in point_ids:
                    point_ids[loc_key] = len(point_ids) + 1
                    point_rows.append({
                        'point_id': point_ids[loc_key],
                        'x': loc[0],
                        'y': loc[1],
                        'z': loc[2] if len(loc) > 2 else None,
                    })
                point_id = point_ids[loc_key]

                card_id = os.path.basename(os.path.dirname(orig_path))
                stem = os.path.splitext(os.path.basename(orig_path))[0]

                # Pad clip before/after the event (clip can't start before the file)
                pad = 1
                clip_offset = max(0, offset - pad)
                clip_duration = row['duration'] + pad + (offset - clip_offset)
                clip_id = f'{stem}_{clip_offset}s.wav'

                if clip_id not in clip_ids:
                    clip_ids.add(clip_id)
                    if not args.dry_run:
                        Audio.from_file(orig_path, offset=clip_offset, duration=clip_duration).save(os.path.join(audio_dir, clip_id))
                    audio_rows.append({
                        'file_id': clip_id,
                        'relative_path': f'audio/{clip_id}',
                        'point_id': point_id,
                        'start_timestamp': row['start_timestamp'],
                        'card_id': card_id,
                    })

                row_file_ids.append(clip_id)
                row_offsets.append(round(offset - clip_offset, 3))

            new_file_ids.append(row_file_ids)
            new_offsets.append(row_offsets)

        df['file_ids'] = new_file_ids
        df['file_start_time_offsets'] = new_offsets

        if not args.dry_run:
            pd.DataFrame(point_rows).to_csv(os.path.join(metadata_dir, 'point_table.csv'), index=False)
            pd.DataFrame(audio_rows).to_csv(os.path.join(metadata_dir, 'audio_file_table.csv'), index=False)
        else:
            print(f'Dry run. Would have exported clips to {audio_dir} and tables to {metadata_dir}')

    columns_to_keep = [
        'event_id', 
        'label', 
        'start_timestamp', 
        'duration', 
        'x',
        'y',
        'z',
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



