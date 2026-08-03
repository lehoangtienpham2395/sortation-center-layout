import glob
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Searching all files for account credentials & hardcoded passwords...")

new_password = 'Tien@giang0203'
target_account = '660021'

found_files = []

for root, dirs, files in os.walk('.'):
    if 'node_modules' in root or '.git' in root or 'dist' in root or '.venv' in root:
        continue
    for file in files:
        if file.endswith(('.py', '.json', '.env', '.txt', '.sh', '.bat', '.ps1', '.js', '.ts')):
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    if '660021' in content or 'SYSTEM_PASSWORD' in content or 'PASSWORD' in content:
                        found_files.append(path)
            except Exception:
                pass

print(f"Found {len(found_files)} files referencing account/password credentials:\n")
for p in found_files:
    print(" -", p)

