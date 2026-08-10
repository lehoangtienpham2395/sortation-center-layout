import os, json, datetime, sys
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

TZ_VN = ZoneInfo('Asia/Ho_Chi_Minh')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHECKPOINT_FILE = os.path.join(BASE_DIR, 'config', 'checkpoint.json')

def get_checkpoint(source_name: str, fallback_str: str) -> str:
    """
    Đọc checkpoint mốc dừng của lần chạy trước.
    Nếu chưa có checkpoint hoặc bị lỗi, trả về fallback_str.
    """
    try:
        if os.path.exists(CHECKPOINT_FILE):
            with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            val = data.get(source_name)
            if val and len(str(val)) >= 10:
                print(f"   🔖 [Checkpoint] Source '{source_name}': Tự động lấy mốc dừng cũ → {val}")
                return str(val)
    except Exception as e:
        print(f"   ⚠️ [Checkpoint] Không đọc được checkpoint cho '{source_name}': {e}")
    
    print(f"   🔖 [Checkpoint] Source '{source_name}': Dùng mốc khởi tạo → {fallback_str}")
    return fallback_str

def save_checkpoint(source_name: str, checkpoint_str: str) -> None:
    """
    Lưu mốc dừng mới sau khi sync thành công.
    """
    try:
        os.makedirs(os.path.dirname(CHECKPOINT_FILE), exist_ok=True)
        data = {}
        if os.path.exists(CHECKPOINT_FILE):
            try:
                with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}
        
        data[source_name] = checkpoint_str
        data['updated_at'] = datetime.datetime.now(TZ_VN).strftime('%Y-%m-%d %H:%M:%S')
        
        with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"   💾 [Checkpoint] Đã lưu mốc dừng mới cho '{source_name}' → {checkpoint_str}")
    except Exception as e:
        print(f"   ⚠️ [Checkpoint] Lỗi lưu checkpoint cho '{source_name}': {e}")
