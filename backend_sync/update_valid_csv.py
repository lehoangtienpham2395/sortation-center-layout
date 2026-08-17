import pandas as pd

valid_path = 'backend_sync/config/valid.csv'
df = pd.read_csv(valid_path, dtype=str)

# Mapping updates for Station_2 -> new Area
station_to_new_area = {
    'SG CHỢ LỚN': 'B00',
    'SG TÂN THỚI HIỆP': 'B04',
    'SG HƯNG LONG': 'B17',
    'SG HÓC MÔN': 'B18',
    'SG BÌNH LỢI': 'B19',
    'SG MINH XUÂN': 'B19',
    'LA ĐỨC HÒA': 'B20',
    'SETN': 'C26',
    '3PL': 'C26',
    'SE TN': 'C26',
    'DN TRẢNG BOM': 'C27',
}

# Update existing rows
for idx, r in df.iterrows():
    st = str(r.get('Station_2') or '').strip()
    ar = str(r.get('area') or '').strip()
    
    if st in station_to_new_area:
        df.at[idx, 'area'] = station_to_new_area[st]
        if st in ('3PL', 'SE TN'):
            df.at[idx, 'Station_2'] = 'SETN'
            
    # Also update any sortcode mapped to old area codes
    if ar == 'C01':
        df.at[idx, 'area'] = 'B00'
    elif ar == 'A03':
        df.at[idx, 'area'] = 'B04'
    elif ar == 'C02':
        df.at[idx, 'area'] = 'B17'
    elif ar == 'A01':
        df.at[idx, 'area'] = 'B18'
    elif ar == 'A02':
        df.at[idx, 'area'] = 'B19'
    elif ar == 'A04':
        df.at[idx, 'area'] = 'B20'

# Check if DN TRẢNG BOM exists, if not add it
if 'DN TRẢNG BOM' not in df['Station_2'].values:
    new_rows = [
        {'sortcode': 'DNI003A', 'Station_2': 'DN TRẢNG BOM', 'area': 'C27', 'Province': 'Đồng Nai'},
        {'sortcode': 'DNI003', 'Station_2': 'DN TRẢNG BOM', 'area': 'C27', 'Province': 'Đồng Nai'},
    ]
    df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)

df.to_csv(valid_path, index=False)
print("✅ Updated valid.csv with new 61-chute layout configuration!")
