import json
import glob
import sys

sys.stdout.reconfigure(encoding='utf-8')

for fp in glob.glob('public/data/*.json'):
    with open(fp, 'r', encoding='utf-8') as f:
        try:
            d = json.load(f)
            if isinstance(d, list):
                for item in d:
                    if isinstance(item, dict):
                        for k, v in item.items():
                            if v == 850 or v == '850':
                                print(f"Found 850 in {fp} under key '{k}': {item}")
                                break
        except Exception as e:
            pass
