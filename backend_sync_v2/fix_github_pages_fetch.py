import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Fixing getApiUrl to fetch directly from local relative path ./data/ for GitHub Pages...")

with open('src/App.tsx', 'r', encoding='utf-8') as f:
    c = f.read()

# Replace getApiUrl implementation to prioritize relative path ./data/
old_get_api_url = '''function getApiUrl(filename: string): string {
  const t = `${Date.now()}_${Math.floor(Math.random() * 100000)}`;
  const isGitHubPages = typeof window !== 'undefined' && (
    window.location.hostname.includes('github.io') ||
    window.location.hostname.includes('githubusercontent.com')
  );
  if (isGitHubPages) {
    return `https://raw.githubusercontent.com/lehoangtienpham2395/sortation-center-layout/main/data/${filename}?t=${t}`;
  }
  return `./data/${filename}?t=${t}`;
}'''

new_get_api_url = '''function getApiUrl(filename: string): string {
  const t = `${Date.now()}_${Math.floor(Math.random() * 100000)}`;
  return `./data/${filename}?t=${t}`;
}'''

if old_get_api_url in c:
    c = c.replace(old_get_api_url, new_get_api_url)
    print("Replaced getApiUrl successfully!")

# Ensure selectedInboundDate defaults to '2026-08-03'
c = c.replace(
    "const [selectedInboundDate, setSelectedInboundDate] = useState<string>('');",
    "const [selectedInboundDate, setSelectedInboundDate] = useState<string>('2026-08-03');"
)

with open('src/App.tsx', 'w', encoding='utf-8') as f:
    f.write(c)

print("✅ App.tsx updated for GitHub Pages fetch optimization!")
