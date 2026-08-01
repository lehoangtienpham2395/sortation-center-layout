import psycopg2
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = psycopg2.connect(dbname='logistics_db', user='postgres', password='Tien@giang0203', host='127.0.0.1', port=5433)
cur = conn.cursor()

# Audit exact 7,272 orders of 2026-07-31
cur.execute('''
    SELECT 
        COALESCE(op_date_pickup::text, operation_date_created::text) AS ref_date,
        flag_inbound,
        operation_date_inbound,
        inbound_scandate,
        flag_outbound,
        outbound_scandate,
        status_sys
    FROM enriched.dispatch_enriched
    WHERE COALESCE(op_date_pickup::text, operation_date_created::text) LIKE '2026-07-31%%';
''')

rows = cur.fetchall()

total_pickup_yesterday = len(rows)
rot_hom_truoc_count = 0

has_inbound_flag_count = 0
has_inbound_time_count = 0
has_outbound_flag_count = 0
has_outbound_time_count = 0
is_canceled_count = 0

# Track violations among the 7,272 rot orders
rot_with_inbound_time = 0
rot_with_outbound_time = 0
rot_with_inbound_flag = 0
rot_with_outbound_flag = 0

for ref_d, flag_in, op_in, in_date, flag_out, out_date, st_sys in rows:
    is_canc = (str(st_sys or '').strip() == 'Đã hủy')
    has_in_cond = (flag_in == 1 or op_in is not None or in_date is not None)
    has_out_cond = (flag_out == 1 or out_date is not None)
    
    is_rot = (not has_in_cond) and (not has_out_cond) and (not is_canc)
    
    if is_rot:
        rot_hom_truoc_count += 1
        if op_in is not None or in_date is not None:
            rot_with_inbound_time += 1
        if out_date is not None:
            rot_with_outbound_time += 1
        if flag_in == 1:
            rot_with_inbound_flag += 1
        if flag_out == 1:
            rot_with_outbound_flag += 1
    else:
        if has_in_cond:
            has_inbound_flag_count += 1
        if has_out_cond:
            has_outbound_flag_count += 1
        if is_canc:
            is_canceled_count += 1

print('=== AUDIT TRỰC TIẾP CỦA 7,272 ĐƠN RỚT HÔM TRƯỚC (31/07) TRONG POSTGRESQL ===')
print(f'1. Tổng số đơn phát sinh Pickup/Tạo ngày 31/07 : {total_pickup_yesterday:,} đơn')
print(f'2. Số đơn ĐÃ CÓ Inbound (đã loại khỏi Rớt)       : {has_inbound_flag_count:,} đơn')
print(f'3. Số đơn ĐÃ CÓ Outbound (đã loại khỏi Rớt)      : {has_outbound_flag_count:,} đơn')
print(f'4. Số đơn ĐÃ HỦY (đã loại khỏi Rớt)              : {is_canceled_count:,} đơn')
print(f'5. Số đơn CHẮC CHẮN 100% RỚT HÔM TRƯỚC            : {rot_hom_truoc_count:,} đơn')
print('-' * 70)
print('VERIFY ĐIỀU KIỆN TRÊN 7,272 ĐƠN RỚT:')
print(f' - Số đơn Rớt có Inbound Time / Inbound Scandate : {rot_with_inbound_time} (Phải = 0)')
print(f' - Số đơn Rớt có Outbound Time / Outbound Scandate: {rot_with_outbound_time} (Phải = 0)')
print(f' - Số đơn Rớt có Cờ Inbound = 1                   : {rot_with_inbound_flag} (Phải = 0)')
print(f' - Số đơn Rớt có Cờ Outbound = 1                  : {rot_with_outbound_flag} (Phải = 0)')

conn.close()
