# data-loca
Acoustic localization annotated dataset metadata


Use `opso-metadata.py` to convervet OpenSoundscape JSON metadata to a standardized format.

How to create at input file:
```
events_dict = {"localized_events": [e.to_dict() for e in localized_events]}
with open(out_file, "w+") as f:
    json.dump(events_dict, f)
```

How to run the script:

```
python opso-metadata.py <input_file>
```