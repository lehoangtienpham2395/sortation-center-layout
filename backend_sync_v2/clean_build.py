import os
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')

# 1. Restore clean dev index.html
dev_index = '''<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate" />
    <meta http-equiv="Pragma" content="no-cache" />
    <meta http-equiv="Expires" content="0" />
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" />
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:ital,wght@0,100..900;1,100..900&family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <title>Layout Master HCM HUB</title>
  </head>
  <body class="bg-[#04070f] text-white">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>'''

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(dev_index)

print("Restored clean dev index.html pointing to /src/main.tsx")

# 2. Run vite build cleanly
res = subprocess.run("npx vite build", shell=True, capture_output=True, text=True)
print("Vite build stdout:", res.stdout)
print("Vite build stderr:", res.stderr)

# 3. Copy dist/index.html over root index.html AFTER build
with open('dist/index.html', 'r', encoding='utf-8') as f:
    dist_c = f.read()

print("Check dist/index.html:")
print("  Shuttle present:", "Shuttle:" in dist_c)
print("  Linehaul present:", "Linehaul:" in dist_c)
print("  Orders Now present:", "Orders Now:" in dist_c)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(dist_c)

print("Singlefile bundle inlined into index.html successfully!")
