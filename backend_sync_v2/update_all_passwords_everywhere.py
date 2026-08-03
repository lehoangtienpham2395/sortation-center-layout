import os
import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Updating SYSTEM_PASSWORD to 'Tien@giang2299' across all Python files and configs...")

new_account = '660021'
new_password = 'Tien@giang2299'

updated_files = []

for root, dirs, files in os.walk('.'):
    if 'node_modules' in root or '.git' in root or 'dist' in root or '.venv' in root:
        continue
    for file in files:
        if file.endswith(('.py', '.json', '.env', '.txt', '.sh', '.bat', '.ps1', '.js', '.ts')):
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                new_content = content
                
                # Replace pattern os.environ.get('SYSTEM_PASSWORD', ... or hardcoded passwords
                # Replace 'Tien@giang...' password strings if matching
                pattern_pass = r"(os\.environ\.get\(\s*['\"]SYSTEM_PASSWORD['\"],?\s*['\"][^'\"]*['\"]\s*\)\s*\.strip\(\)\s*or\s*['\"])([^'\"]*)(['\"])"
                new_content = re.sub(pattern_pass, r"\g<1>Tien@giang2299\3", new_content)
                
                pattern_acc = r"(os\.environ\.get\(\s*['\"]SYSTEM_ACCOUNT['\"],?\s*['\"][^'\"]*['\"]\s*\)\s*\.strip\(\)\s*or\s*['\"])([^'\"]*)(['\"])"
                new_content = re.sub(pattern_acc, r"\g<1>660021\3", new_content)
                
                # Replace direct string assignments if present
                if 'SYSTEM_PASSWORD' in new_content or 'Tien@giang' in content:
                    # Also replace any occurrence of old password variations
                    new_content = re.sub(r"['\"]Tien@giang0203['\"]", f"'{new_password}'", new_content)
                    new_content = re.sub(r"['\"]Tien@giang2209['\"]", f"'{new_password}'", new_content)
                    new_content = re.sub(r"['\"]Tien@giang2299['\"]", f"'{new_password}'", new_content)
                
                if new_content != content:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    updated_files.append(path)
                    print(f"Updated credentials in: {path}")
            except Exception as e:
                print(f"Error processing {path}: {e}")

print(f"\n✅ Total {len(updated_files)} files updated with password 'Tien@giang2299'!")
