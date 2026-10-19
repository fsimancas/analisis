import json
import urllib.request
import gzip
import time

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://www.fotmob.com/',
    'Origin': 'https://www.fotmob.com'
}

with open('all_leagues_fotmob.json', 'r', encoding='utf-8') as f:
    fm_raw = json.load(f)

# All authentic leagues from FotMob raw
raw_leagues_map = {}
for grp in ['popular', 'international', 'countries']:
    items = fm_raw.get(grp, [])
    if grp == 'popular':
        for l in items:
            raw_leagues_map[l['id']] = (l['name'], 'Popular')
    elif grp == 'international':
        for c in items:
            for l in c.get('leagues', []):
                raw_leagues_map[l['id']] = (l['name'], c.get('name'))
    else:
        for c in items:
            for l in c.get('leagues', []):
                raw_leagues_map[l['id']] = (l['name'], c.get('name'))

print(f"Total authentic leagues in FotMob raw JSON: {len(raw_leagues_map)}")

# Test a few known good ones to verify the test logic
for test_id in [42, 47, 54, 55, 87, 45, 299, 9490, 8965]:
    name, country = raw_leagues_map.get(test_id, ('Unknown', 'Unknown'))
    try:
        req = urllib.request.Request(f'https://www.fotmob.com/api/data/leagues?id={test_id}', headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            print(f"[HTTP 200] ID {test_id}: {name} ({country})")
    except Exception as e:
        print(f"[FAIL] ID {test_id}: {e}")
