"""Geocoding audit — validates Latitude/Longitude using country bounding boxes."""
import pandas as pd

programs = {
    'sustainable_development': 'programs/sustainable_development/thesis_metadata_matched.csv',
    'energy_science':          'programs/energy_science/thesis_metadata_matched.csv',
    'innovation_sciences':     'programs/innovation_sciences/thesis_metadata_matched.csv',
    'sbi':                     'programs/sbi/thesis_metadata_matched.csv',
    'water_management':        'programs/water_management/thesis_metadata_matched.csv',
}

NL_DEFAULT_LAT = 52.243498
NL_DEFAULT_LON = 5.634323

# (min_lat, max_lat, min_lon, max_lon) — generous boxes; use only for clear outliers
COUNTRY_BOUNDS = {
    'NL': (50.75, 53.55,  3.35,  7.23),
    'DE': (47.27, 55.06,  5.87, 15.04),
    'FR': (41.33, 51.09, -5.14, 10.00),
    'ES': (35.95, 43.97, -9.30,  4.59),
    'IT': (35.49, 47.09,  6.62, 18.78),
    'BE': (49.50, 51.51,  2.54,  6.41),
    'AT': (46.38, 49.02,  9.53, 17.16),
    'CH': (45.82, 47.81,  5.96, 10.49),
    'PL': (49.00, 54.84, 14.12, 24.15),
    'PT': (36.96, 42.15, -9.52, -6.19),
    'SE': (55.34, 69.06, 10.96, 24.17),
    'NO': (57.98, 71.19,  4.09, 31.27),
    'DK': (54.56, 57.75,  8.07, 15.20),
    'FI': (59.81, 70.09, 19.09, 31.59),
    'GB': (49.87, 60.85,-14.02,  2.02),
    'US': (24.52, 49.38,-124.77,-66.95),
    'CA': (41.68, 83.12,-141.00,-52.62),
    'MX': (14.53, 32.72,-117.12,-86.70),
    'BR': (-33.75,  5.27,-73.98,-34.79),
    'CO': ( -4.23, 12.46,-81.73,-66.87),
    'PE': (-18.35,  0.04,-81.33,-68.65),
    'EC': ( -5.02,  1.67,-81.00,-75.19),
    'AR': (-55.06,-21.78,-73.56,-53.64),
    'CL': (-55.92,-17.49,-75.64,-66.42),
    'BO': (-22.90, -9.67,-69.65,-57.45),
    'UY': (-34.95,-30.08,-58.44,-53.09),
    'VE': ( -0.64, 12.20,-73.35,-59.80),
    'CR': (  8.03, 11.22,-85.95,-82.56),
    'GT': ( 13.74, 17.82,-92.23,-88.22),
    'HN': ( 12.98, 16.01,-89.36,-83.15),
    'NI': ( 10.71, 15.03,-87.69,-83.15),
    'IN': (  8.07, 37.10, 68.11, 97.41),
    'CN': ( 18.16, 53.56, 73.50,134.77),
    'JP': ( 24.04, 45.71,122.93,153.98),
    'KR': ( 33.11, 38.61,124.61,130.91),
    'ID': (-11.01,  5.91, 95.01,141.02),
    'MY': ( -4.64,  7.36,100.09,119.27),
    'SG': (  1.15,  1.48,103.60,104.05),
    'VN': (  8.56, 23.39,102.14,109.47),
    'TH': (  5.63, 20.47, 97.34,105.64),
    'BD': ( 20.74, 26.63, 88.01, 92.68),
    'PK': ( 23.69, 37.08, 60.87, 77.83),
    'LK': (  5.92,  9.84, 79.65, 81.88),
    'NP': ( 26.35, 30.45, 80.06, 88.20),
    'PH': (  4.64, 21.12,116.93,126.60),
    'KE': ( -4.67,  4.62, 33.91, 41.90),
    'TZ': (-11.74, -0.99, 29.34, 40.44),
    'UG': ( -1.48,  4.23, 29.57, 35.00),
    'ET': (  3.40, 15.00, 32.99, 47.99),
    'GH': (  4.71, 11.17, -3.26,  1.19),
    'NG': (  4.27, 13.87,  2.67, 14.68),
    'ZA': (-34.83,-22.13, 16.46, 32.89),
    'ZW': (-22.42,-15.61, 25.24, 33.07),
    'ZM': (-18.08, -8.22, 21.97, 33.71),
    'MZ': (-26.87,-10.47, 30.22, 40.84),
    'MW': (-17.13, -9.37, 32.67, 35.92),
    'RW': ( -2.84,  -1.05, 28.86, 30.90),
    'SN': ( 12.31, 16.69,-17.54,-11.36),
    'CM': (  1.65, 13.08,  8.50, 16.19),
    'MA': ( 27.66, 35.92,-13.17,  2.00),
    'EG': ( 22.00, 31.58, 24.70, 37.22),
    'TR': ( 35.82, 42.11, 25.66, 44.82),
    'IR': ( 25.05, 39.77, 44.02, 63.33),
    'JO': ( 29.19, 33.38, 34.96, 39.30),
    'AU': (-43.64,-10.67,113.16,153.64),
    'RU': ( 41.19, 81.88, 19.64,180.00),
    'UA': ( 44.39, 52.38, 22.14, 40.23),
}

# Maps CSV country keywords → ISO code
COUNTRY_KEY = {
    'netherlands': 'NL', 'germany': 'DE', 'france': 'FR', 'spain': 'ES',
    'italy': 'IT', 'colombia': 'CO', 'brazil': 'BR', 'chile': 'CL',
    'peru': 'PE', 'ecuador': 'EC', 'argentina': 'AR', 'mexico': 'MX',
    'india': 'IN', 'china': 'CN', 'indonesia': 'ID', 'kenya': 'KE',
    'ethiopia': 'ET', 'ghana': 'GH', 'nigeria': 'NG', 'south africa': 'ZA',
    'tanzania': 'TZ', 'uganda': 'UG', 'united kingdom': 'GB', 'england': 'GB',
    'sweden': 'SE', 'norway': 'NO', 'denmark': 'DK', 'finland': 'FI',
    'united states': 'US', 'usa': 'US', 'costa rica': 'CR', 'bolivia': 'BO',
    'canada': 'CA', 'australia': 'AU', 'bangladesh': 'BD', 'pakistan': 'PK',
    'vietnam': 'VN', 'thailand': 'TH', 'morocco': 'MA', 'egypt': 'EG',
    'zimbabwe': 'ZW', 'zambia': 'ZM', 'mozambique': 'MZ', 'malawi': 'MW',
    'rwanda': 'RW', 'portugal': 'PT', 'belgium': 'BE', 'austria': 'AT',
    'switzerland': 'CH', 'poland': 'PL', 'ukraine': 'UA', 'philippines': 'PH',
    'sri lanka': 'LK', 'nepal': 'NP', 'myanmar': 'MM', 'jordan': 'JO',
    'cameroon': 'CM', 'honduras': 'HN', 'guatemala': 'GT', 'nicaragua': 'NI',
    'venezuela': 'VE', 'uruguay': 'UY', 'russia': 'RU', 'japan': 'JP',
    'south korea': 'KR', 'malaysia': 'MY', 'singapore': 'SG',
    'senegal': 'SN', 'turkey': 'TR', 'iran': 'IR', 'paraguay': 'PY',
}


def in_bounds(lat, lon, cc):
    if cc not in COUNTRY_BOUNDS:
        return True  # can't check → skip
    minlat, maxlat, minlon, maxlon = COUNTRY_BOUNDS[cc]
    return minlat <= lat <= maxlat and minlon <= lon <= maxlon


issues = []

for prog, path in programs.items():
    try:
        df = pd.read_csv(path)
    except Exception as e:
        print(f"Could not load {path}: {e}")
        continue

    for _, row in df.iterrows():
        try:
            lat = float(row.get('Latitude'))
            lon = float(row.get('Longitude'))
        except (ValueError, TypeError):
            continue

        country_csv = str(row.get('Country', '')).strip()

        # Skip NL fallback centre
        if abs(lat - NL_DEFAULT_LAT) < 0.001 and abs(lon - NL_DEFAULT_LON) < 0.001:
            continue

        csv_lower = country_csv.lower()
        expected_cc = None
        for keyword, cc in COUNTRY_KEY.items():
            if keyword in csv_lower:
                expected_cc = cc
                break

        if not expected_cc:
            continue

        if not in_bounds(lat, lon, expected_cc):
            issues.append({
                'prog': prog,
                'author': str(row.get('Author(s)', ''))[:45],
                'title': str(row.get('Title', ''))[:80],
                'geo_loc': str(row.get('Geographical location standardized', '')),
                'lat': lat,
                'lon': lon,
                'csv_country': country_csv,
                'expected_cc': expected_cc,
            })

print(f"\n{'='*80}")
print(f"GEOCODING AUDIT (bbox) — {len(issues)} confirmed mismatches")
print(f"{'='*80}\n")
for i, iss in enumerate(issues, 1):
    print(f"[{i}] [{iss['prog']}]")
    print(f"    Author  : {iss['author']}")
    print(f"    Title   : {iss['title']}")
    print(f"    Geo loc : {iss['geo_loc']}")
    print(f"    Coords  : {iss['lat']}, {iss['lon']}")
    print(f"    CSV ctry: {iss['csv_country']}  (expected {iss['expected_cc']})")
    print()
