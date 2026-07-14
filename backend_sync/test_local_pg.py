import psycopg2
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Thử các thông tin kết nối phổ biến
credentials = [
    {"host": "localhost", "user": "postgres", "password": "postgres", "dbname": "postgres"},
    {"host": "localhost", "user": "postgres", "password": "admin", "dbname": "postgres"},
    {"host": "localhost", "user": "postgres", "password": "123", "dbname": "postgres"},
    {"host": "localhost", "user": "postgres", "password": "123456", "dbname": "postgres"},
]

success = False
for cred in credentials:
    try:
        conn = psycopg2.connect(**cred)
        print(f"✅ Kết nối thành công bằng: user={cred['user']}, password={cred['password']}")
        conn.close()
        success = True
        break
    except Exception as e:
        print(f"❌ Thử user={cred['user']}, password={cred['password']} thất bại: {e}")

if not success:
    print("\n👉 Vui lòng cho biết: Username, Password, Cổng (Port, mặc định 5432) và Database Name của Postgres trên máy bro.")
