"""
TEST CSV ONLY -- Chay pipeline_unified_v6 nhung KHONG ghi vao PostgreSQL.
Chan module psycopg2 de Phase 6 (DB) bi skip, chi xuat CSV (Phase 7).
Dung de test truoc khi dua du lieu len DB.
"""

import os
import sys
import time
import importlib

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# Chan psycopg2 -> `import psycopg2` trong Phase 6 se raise ImportError,
# bi except bat -> skip PostgreSQL, tiep tuc sang Phase 7 (CSV).
sys.modules['psycopg2'] = None

if __name__ == "__main__":
    import pipeline_unified_v6

    days = 7
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1].replace('--days=', '').strip())
        except ValueError:
            pass

    pipeline_unified_v6.DAYS_BACK = days
    sys.argv = [sys.argv[0], f'--days={days}']

    t0 = time.time()
    pipeline_unified_v6.main()

    csv_path = pipeline_unified_v6.OUTPUT_FILE
    print('\n' + '=' * 65)
    print(f'TEST CSV-ONLY HOAN TAT trong {round(time.time() - t0, 1)}s')
    print(f'CSV output : {csv_path} (exists={os.path.exists(csv_path)})')
    if os.path.exists(csv_path):
        import pandas as pd
        df = pd.read_csv(csv_path)
        print(f'Rows       : {len(df):,}')
        print(f'Columns    : {list(df.columns)}')
    print('=' * 65)
