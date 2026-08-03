import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Inspecting data/inventory.json sample structure...")

with open('data/inventory.json', 'r', encoding='utf-8') as f:
    inv = json.load(f)

print(f"Total inventory records: {len(inv)}")
if len(inv) > 0:
    print("Sample record 1:", inv[0])
    if len(inv) > 1:
        print("Sample record 2:", inv[1])
