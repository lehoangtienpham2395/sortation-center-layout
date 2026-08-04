import json
import os

files_to_reset = [
    'data/inventory.json',
    'data/outbound.json',
    'data/backlog.json',
    'public/data/inventory.json',
    'public/data/outbound.json',
    'public/data/backlog.json',
    'src/data/inventory.json',
    'src/data/outbound.json',
    'src/data/backlog.json',
]

for fp in files_to_reset:
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump([], f, indent=2)
    print(f"Reset {fp} to []")

print("All layout JSON files reset to empty [].")
