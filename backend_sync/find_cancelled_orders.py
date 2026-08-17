import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

conn = get_pg_conn()
tables = pd.read_sql("""
    SELECT table_schema, table_name 
    FROM information_schema.tables 
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema');
""", conn)
print("Tables in Postgres:")
print(tables.to_string())

# Check columns of all tables
for _, row in tables.iterrows():
    schema = row['table_schema']
    table = row['table_name']
    cols_df = pd.read_sql(f"""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_schema = '{schema}' AND table_name = '{table}';
    """, conn)
    cols = cols_df['column_name'].tolist()
    print(f"\n{schema}.{table} columns: {cols}")

conn.close()
