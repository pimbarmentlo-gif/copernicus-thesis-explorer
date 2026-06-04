"""Apply confirmed geocoding fixes."""
import pandas as pd

fixes = [
    # (programme, author_substr, new_lat, new_lon, note)
    ('water_management',       'Noordam',    30.7417,   31.7191,  'Sharkia Governorate, Egypt (was Saudi Arabia)'),
    ('innovation_sciences',    'Corrà',      38.9072,  -77.0369,  'Washington D.C. (was US geographic center)'),
    ('sbi',                    'Neudeck',    48.2082,   16.3738,  'Vienna, Austria (was generic Austria coord)'),
    ('sustainable_development','Gödde',      54.7934,    9.4296,  'Flensburg, Germany (was Germany center)'),
    ('sustainable_development','Budie',      22.9868,   87.8550,  'West Bengal, India (was India center)'),
    ('sustainable_development','Barmentlo',  47.2565,   11.6016,  'Tirol, Austria (was Styria generic coord)'),
    ('sustainable_development','Kelly',      36.0611,  103.8340,  'Yellow River / Lanzhou, China (was China center)'),
    ('innovation_sciences',    'Wirp',       52.2730,    8.0470,  'Osnabrück, Germany (was Germany center)'),
]

paths = {
    'sustainable_development': 'programs/sustainable_development/thesis_metadata_matched.csv',
    'energy_science':          'programs/energy_science/thesis_metadata_matched.csv',
    'innovation_sciences':     'programs/innovation_sciences/thesis_metadata_matched.csv',
    'sbi':                     'programs/sbi/thesis_metadata_matched.csv',
    'water_management':        'programs/water_management/thesis_metadata_matched.csv',
}

dfs = {k: pd.read_csv(v) for k, v in paths.items()}

for prog, author, new_lat, new_lon, note in fixes:
    df = dfs[prog]
    mask = df['Author(s)'].str.contains(author, na=False)
    if mask.sum() == 0:
        print(f"WARNING: no row found for '{author}' in {prog}")
        continue
    if mask.sum() > 1:
        print(f"WARNING: {mask.sum()} rows match '{author}' in {prog} — taking first")
    idx = df[mask].index[0]
    old_lat = df.at[idx, 'Latitude']
    old_lon = df.at[idx, 'Longitude']
    df.at[idx, 'Latitude']  = new_lat
    df.at[idx, 'Longitude'] = new_lon
    df.at[idx, 'All_Latitudes']  = new_lat
    df.at[idx, 'All_Longitudes'] = new_lon
    print(f"[{prog}] {df.at[idx, 'Author(s)']} — {note}")
    print(f"   ({old_lat}, {old_lon}) → ({new_lat}, {new_lon})")

for prog, path in paths.items():
    dfs[prog].to_csv(path, index=False)
    print(f"Saved {path}")
