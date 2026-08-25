"""
Check whether a DataLoca dataset folder can be used to run OpenSoundscape's
SynchronizedRecorderArray.localize_detections().

Expects a folder following DataLoca-standard.md:
    <dataset_dir>/
    ├── localized_events.csv
    ├── localization_metadata/
    │   ├── point_table.csv
    │   └── audio_file_table.csv
    └── audio/

How to run the script:
    python dataloca-check.py <dataset_dir>
    python dataloca-check.py <dataset_dir> --min-n-receivers 4 --max-receiver-dist 100
    python dataloca-check.py <dataset_dir> --sample 20

Exits with status 1 if any check fails.
"""


import pandas as pd
import os
import re
import ast
import sys
import time
import argparse

from opensoundscape import Audio
from opensoundscape.localization import SynchronizedRecorderArray


events_filename = 'localized_events.csv'
metadata_dirname = 'localization_metadata'
point_table_filename = 'point_table.csv'
audio_file_table_filename = 'audio_file_table.csv'
audio_dirname = 'audio'

events_required_columns = ['event_id', 'label', 'start_timestamp', 'duration', 'file_ids', 'file_start_time_offsets']
point_required_columns = ['point_id', 'x', 'y']
audio_file_required_columns = ['file_id', 'relative_path', 'point_id']

default_min_n_receivers = 4
default_max_receiver_dist = 100

checklist_report_filename = 'checklist_report.csv'
default_checklist_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'DataLoca-standard-checklist.md')

# (checklist section number, regex matched against the item text, checklist_key)
# checklist_key ties a checklist bullet to the log_result() call(s) that verify it.
checklist_key_map = [
    (1, r'localized_events\.csv.*present at top level', 'events_file_present'),
    (1, r'`point_table\.csv`', 'point_table_present'),
    (1, r'`audio_file_table\.csv`', 'audio_file_table_present'),
    (1, r'/audio/.*subfolder containing every audio file referenced', 'audio_files_present'),
    (2, r'file_ids.*each value exists in `audio_file_table\.csv`', 'event_file_ids_exist'),
    (2, r'file_start_time_offsets.*one offset.*per entry in `file_ids`', 'file_ids_offsets_match_length'),
    (2, r'start_timestamp.*ISO format, including UTC offset', 'timestamps_tz_aware'),
    (3, r'point_id.*unique; matches the `point_id` values used in `audio_file_table\.csv`', 'point_id_unique_and_referenced'),
    (3, r'microphone position in', 'point_coords_complete'),
    (4, r'point_id.*matches a `point_id` in `point_table\.csv`', 'point_id_unique_and_referenced'),
    (4, r'relative_path.*resolves to the actual file', 'audio_files_present'),
    (5, r'Contains every file referenced by `relative_path`', 'audio_files_present'),
]

status_severity = {'PASS': 0, 'WARN': 1, 'FAIL': 2}

results = []
key_results = {}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_dir", type=str, help = 'Path to DataLoca dataset folder.')
    parser.add_argument("--min-n-receivers", dest="min_n_receivers", type = int, default=default_min_n_receivers, help = "Minimum number of receivers for an event to be localized.")
    parser.add_argument("--max-receiver-dist", dest="max_receiver_dist", type = float, default=default_max_receiver_dist, help = "Maximum distance between receivers, in meters.")
    parser.add_argument("--sample", type = int, default=None, help = "Take a smaller sample of events for debugging.")
    parser.add_argument("--checklist", type=str, default=default_checklist_path, help = "Path to DataLoca-standard-checklist.md, used to generate checklist_report.csv.")

    return parser.parse_args()


def log_result(status, name, message, checklist_keys=None):
    results.append(status)
    print(f'[{status:4}] {name}: {message}')
    if checklist_keys:
        if isinstance(checklist_keys, str):
            checklist_keys = [checklist_keys]
        for key in checklist_keys:
            key_results.setdefault(key, []).append((status, message))


def parse_checklist(checklist_path):
    """Parse DataLoca-standard-checklist.md into one row per '- [ ]' item, tagged with its section and checklist_key (if any)."""
    items = []
    section_num, section_title = None, None
    with open(checklist_path, 'r') as f:
        for line in f:
            header_match = re.match(r'^##\s+(\d+)\.\s+(.+?)\s*$', line)
            if header_match:
                section_num = int(header_match.group(1))
                section_title = f'{section_num}. {header_match.group(2)}'
                continue
            item_match = re.match(r'^\s*-\s\[ \]\s?(.+?)\s*$', line)
            if item_match and section_num is not None:
                text = item_match.group(1)
                key = next((k for sec, pattern, k in checklist_key_map if sec == section_num and re.search(pattern, text)), None)
                items.append({'section': section_title, 'item': text, 'key': key})
    return items


def write_checklist_report(dataset_dir, checklist_items):
    rows = []
    for item in checklist_items:
        status, message = '', ''
        entries = key_results.get(item['key']) if item['key'] else None
        if entries:
            status = max(entries, key=lambda e: status_severity.get(e[0], 0))[0]
            message = '; '.join(m for _, m in entries)
        rows.append({'section': item['section'], 'item': item['item'], 'status': status, 'message': message})

    report_path = os.path.join(dataset_dir, checklist_report_filename)
    pd.DataFrame(rows).to_csv(report_path, index=False, encoding='utf-8-sig')
    print(f'Checklist report written to {report_path}')


def finish(run_start):
    n_fail = results.count('FAIL')
    print(f'\n{results.count("PASS")} passed, {results.count("WARN")} warnings, {n_fail} failed. Elapsed {time.time() - run_start:.1f}s')
    if checklist_items is not None:
        write_checklist_report(dataset_dir, checklist_items)
    sys.exit(1 if n_fail else 0)


def parse_list_column(value):
    return ast.literal_eval(value) if isinstance(value, str) else value


# #-------------------------------------------------------------------------------------
if __name__ == "__main__":
    args = parse_args()

    run_start = time.time()
    dataset_dir = os.path.abspath(args.dataset_dir)

    try:
        checklist_items = parse_checklist(args.checklist)
    except OSError as exc:
        print(f'WARNING: could not read checklist at {args.checklist} ({exc}); skipping checklist_report.csv')
        checklist_items = None

    # Folder structure -----------------------------------------------------------------
    events_path = os.path.join(dataset_dir, events_filename)
    point_path = os.path.join(dataset_dir, metadata_dirname, point_table_filename)
    audio_file_path = os.path.join(dataset_dir, metadata_dirname, audio_file_table_filename)
    audio_dir = os.path.join(dataset_dir, audio_dirname)

    structure_checks = [
        (events_path, 'localized_events.csv', 'events_file_present'),
        (point_path, 'point_table.csv', 'point_table_present'),
        (audio_file_path, 'audio_file_table.csv', 'audio_file_table_present'),
        (audio_dir, 'audio/', 'audio_files_present'),
    ]
    for path, label, key in structure_checks:
        if os.path.exists(path):
            log_result('PASS', 'structure', f'{label} found', checklist_keys=key)
        else:
            log_result('FAIL', 'structure', f'{label} missing', checklist_keys=key)

    if results.count('FAIL') > 0:
        finish(run_start)

    events = pd.read_csv(events_path)
    points = pd.read_csv(point_path)
    audio_file_table = pd.read_csv(audio_file_path)

    # Required columns -----------------------------------------------------------------
    tables_to_check = [
        (events_filename, events, events_required_columns),
        (point_table_filename, points, point_required_columns),
        (audio_file_table_filename, audio_file_table, audio_file_required_columns)]

    for table_name, table, required_columns in tables_to_check:
        missing_columns = [c for c in required_columns if c not in table.columns]
        if missing_columns:
            log_result('FAIL', 'columns', f'{table_name} missing {missing_columns}')
        else:
            log_result('PASS', 'columns', f'{table_name} has all required columns')

    if results.count('FAIL') > 0:
        finish(run_start)

    if args.sample is not None:
        events = events.head(args.sample)
        print(f'\nUsing a sample of {len(events)} events.\n')

    # Table keys -----------------------------------------------------------------------
    if audio_file_table['file_id'].duplicated().any():
        log_result('FAIL', 'keys', f'{audio_file_table_filename} has duplicate file_id values')
    else:
        log_result('PASS', 'keys', f'{len(audio_file_table)} unique file_id values')

    if points['point_id'].duplicated().any():
        log_result('FAIL', 'keys', f'{point_table_filename} has duplicate point_id values', checklist_keys='point_id_unique_and_referenced')
    else:
        log_result('PASS', 'keys', f'{len(points)} unique point_id values', checklist_keys='point_id_unique_and_referenced')

    orphan_points = sorted(set(audio_file_table['point_id']) - set(points['point_id']))
    if orphan_points:
        log_result('FAIL', 'keys', f'{len(orphan_points)} point_id in audio_file_table missing from point_table, e.g. {orphan_points[:3]}', checklist_keys='point_id_unique_and_referenced')
    else:
        log_result('PASS', 'keys', 'every point_id in audio_file_table is in point_table', checklist_keys='point_id_unique_and_referenced')

    # List columns pair up per event
    ragged_events = [
        event['event_id'] for _, event in events.iterrows()
        if len(parse_list_column(event['file_ids'])) != len(parse_list_column(event['file_start_time_offsets']))]
    if ragged_events:
        log_result('FAIL', 'events', f'{len(ragged_events)} events have file_ids and file_start_time_offsets of different lengths, e.g. {ragged_events[:3]}', checklist_keys='file_ids_offsets_match_length')
        finish(run_start)
    log_result('PASS', 'events', f'{len(events)} events have matching file_ids and file_start_time_offsets lengths', checklist_keys='file_ids_offsets_match_length')

    event_file_ids = sorted({file_id for value in events['file_ids'] for file_id in parse_list_column(value)})
    known_file_ids = set(audio_file_table['file_id'])
    orphan_file_ids = [f for f in event_file_ids if f not in known_file_ids]
    if orphan_file_ids:
        log_result('FAIL', 'keys', f'{len(orphan_file_ids)} file_ids in {events_filename} missing from audio_file_table, e.g. {orphan_file_ids[:3]}', checklist_keys='event_file_ids_exist')
        finish(run_start)
    log_result('PASS', 'keys', f'all {len(event_file_ids)} referenced file_ids are in audio_file_table', checklist_keys='event_file_ids_exist')

    # Audio files ----------------------------------------------------------------------
    audio_path_by_file_id = {
        file_id: os.path.join(dataset_dir, relative_path)
        for file_id, relative_path in zip(audio_file_table['file_id'], audio_file_table['relative_path'])}

    missing_audio = [f for f in event_file_ids if not os.path.exists(audio_path_by_file_id[f])]
    if missing_audio:
        log_result('FAIL', 'audio', f'{len(missing_audio)} audio files not found on disk, e.g. {missing_audio[:3]}', checklist_keys='audio_files_present')
        finish(run_start)
    log_result('PASS', 'audio', f'all {len(event_file_ids)} audio files found on disk', checklist_keys='audio_files_present')

    unreadable_audio = []
    audio_without_timestamp = []
    for file_id in event_file_ids:
        try:
            metadata = Audio.from_file(audio_path_by_file_id[file_id], duration=0.0001).metadata
        except Exception as exc:
            unreadable_audio.append(f'{file_id} ({type(exc).__name__})')
            continue
        if metadata is None or metadata.get('recording_start_time') is None:
            audio_without_timestamp.append(file_id)

    if unreadable_audio:
        log_result('FAIL', 'audio', f'{len(unreadable_audio)} audio files could not be opened, e.g. {unreadable_audio[:3]}')
        finish(run_start)
    log_result('PASS', 'audio', f'all {len(event_file_ids)} audio files opened successfully')

    # recording_start_time is only a fallback: start_timestamp is supplied from localized_events.csv
    if audio_without_timestamp:
        log_result('WARN', 'audio', f'{len(audio_without_timestamp)} audio files have no recording_start_time metadata, e.g. {audio_without_timestamp[:3]}')
    else:
        log_result('PASS', 'audio', 'all audio files carry recording_start_time metadata')

    # Receiver coordinates -------------------------------------------------------------
    coordinate_columns = ['x', 'y', 'z'] if 'z' in points.columns and points['z'].notna().all() else ['x', 'y']
    point_coordinates = points.set_index('point_id')[coordinate_columns]

    file_coords = audio_file_table.set_index('file_id').join(point_coordinates, on='point_id')[coordinate_columns]
    file_coords = file_coords.loc[event_file_ids]
    file_coords.index = [audio_path_by_file_id[f] for f in file_coords.index]

    if file_coords.isna().any().any():
        log_result('FAIL', 'coords', f'{int(file_coords.isna().any(axis=1).sum())} files have missing coordinate values', checklist_keys='point_coords_complete')
        finish(run_start)
    log_result('PASS', 'coords', f'{len(file_coords)} files have complete {"".join(coordinate_columns)} coordinates', checklist_keys='point_coords_complete')

    # Detections table -----------------------------------------------------------------
    detection_rows = []
    for _, event in events.iterrows():
        start_timestamp = pd.Timestamp(event['start_timestamp'])
        for file_id, offset in zip(parse_list_column(event['file_ids']), parse_list_column(event['file_start_time_offsets'])):
            detection_rows.append({
                'file': audio_path_by_file_id[file_id],
                'start_time': float(offset),
                'end_time': float(offset) + float(event['duration']),
                'start_timestamp': start_timestamp,
                'label': event['label']})

    detections = pd.DataFrame(detection_rows)

    if not all(t.tzinfo is not None and t.tzinfo.utcoffset(t) is not None for t in detections['start_timestamp']):
        log_result('FAIL', 'timestamps', 'start_timestamp values are not all timezone-aware', checklist_keys='timestamps_tz_aware')
        finish(run_start)
    log_result('PASS', 'timestamps', f'{detections["start_timestamp"].nunique()} unique timezone-aware start_timestamps', checklist_keys='timestamps_tz_aware')

    class_columns = pd.get_dummies(detections['label']).astype(int)
    detections = pd.concat([detections.drop(columns='label'), class_columns], axis=1)
    detections = detections.set_index(['file', 'start_time', 'end_time', 'start_timestamp'])
    detections = detections.groupby(level=['file', 'start_time', 'end_time', 'start_timestamp']).max()

    array = SynchronizedRecorderArray(file_coords)

    files_missing_coordinates = array.check_files_missing_coordinates(detections)
    if files_missing_coordinates:
        log_result('FAIL', 'coords', f'{len(files_missing_coordinates)} detection files missing from file_coords, e.g. {files_missing_coordinates[:3]}', checklist_keys='point_coords_complete')
        finish(run_start)
    log_result('PASS', 'coords', 'every detection file has coordinates', checklist_keys='point_coords_complete')

    # Receiver density -----------------------------------------------------------------
    # Mirrors create_candidate_events(): a timestamp yields an event only if some reference
    # receiver has min_n_receivers-1 other detecting receivers within max_receiver_dist.
    nearby_files_dict = array.make_nearby_files_dict(args.max_receiver_dist)

    feasible_timestamps = 0
    for _, detections_at_time in detections.groupby(level='start_timestamp'):
        files_with_detections = set(detections_at_time.reset_index()['file'])
        if len(files_with_detections) < args.min_n_receivers:
            continue
        for reference_file in files_with_detections:
            close_detection_files = files_with_detections.intersection(nearby_files_dict[reference_file])
            if len(close_detection_files) + 1 >= args.min_n_receivers:
                feasible_timestamps += 1
                break

    if feasible_timestamps == 0:
        log_result('FAIL', 'density', f'no timestamp has {args.min_n_receivers} receivers within {args.max_receiver_dist} m')
    else:
        log_result('PASS', 'density', f'{feasible_timestamps} of {detections.index.get_level_values("start_timestamp").nunique()} timestamps can form a candidate event')

    # Run localization -----------------------------------------------------------------
    localize_start = time.time()
    try:
        position_estimates = array.localize_detections(
            detections=detections,
            min_n_receivers=args.min_n_receivers,
            max_receiver_dist=args.max_receiver_dist)
        if len(position_estimates) == 0:
            log_result('FAIL', 'localize_detections', f'ran without error but returned 0 position estimates in {time.time() - localize_start:.1f}s')
        else:
            log_result('PASS', 'localize_detections', f'returned {len(position_estimates)} position estimates in {time.time() - localize_start:.1f}s')
    except Exception as exc:
        log_result('FAIL', 'localize_detections', f'{type(exc).__name__}: {exc}')

    finish(run_start)
