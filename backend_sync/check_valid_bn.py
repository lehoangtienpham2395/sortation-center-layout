import os, pandas as pd

valid_path = os.path.join('backend_sync', 'config', 'valid.csv')
df = pd.read_csv(valid_path, encoding='utf-8-sig')

# Find BN HUB or Linehaul in valid.csv
df_bn = df[(df['Mã khu vực'] == 'A06') | (df['Tên bưu cục'].str.contains('BN HUB', na=False)) | (df['Tên điểm tiếp theo'].str.contains('BN HUB', na=False))]
print("Valid.csv rows mapped to A06 / BN HUB:")
print(df_bn.to_string())

# Check sortcodes starting with HNI, BNI, HPG, PTH, NBI in valid.csv
sample_scs = ['HNI033A', 'HNI049A', 'HNI050M', 'BNI001A', 'HPG005A', 'HNI010A', 'HNI046A', 'HNI038A', 'PTH009A', 'HNI009A', 'BNI006A', 'HNI027A', 'HNI031A', 'BNI004A', 'HNI020A', 'NBI001A', 'BNI007A', 'HNI045A', 'HNI008A']
found_scs = df[df['sortcode'].isin(sample_scs)]
print("\nFound sample sortcodes in valid.csv:")
print(found_scs)
