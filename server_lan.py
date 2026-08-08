import http.server
import socketserver
import socket
import webbrowser
import sys
import os

# Set directory to dist/ (singlefile production bundle) if it exists
project_dir = os.path.dirname(os.path.abspath(__file__))
dist_dir = os.path.join(project_dir, 'dist')

if os.path.exists(os.path.join(dist_dir, 'index.html')):
    os.chdir(dist_dir)
else:
    os.chdir(project_dir)

class CustomHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        super().end_headers()

PORT = 5173

# Detect LAN IP
lan_ip = "10.40.5.3"
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('8.8.8.8', 80))
    detected = s.getsockname()[0]
    if detected:
        lan_ip = detected
    s.close()
except Exception:
    pass

print("=" * 70)
print("  J&T CARGO HCM HUB DASHBOARD - LUONG CHAY MANG NOI BO (LAN INTRANET)")
print("=" * 70)
print(f"\n  >>> LINK TRUY CAP NOI BO CHO TOAN BO CONG NHAN / BUU CUC: <<<\n")
print(f"        http://{lan_ip}:{PORT}/\n")
print("  (Moi may tinh, dien thoai, iPad ket noi cung Wi-Fi / LAN deu xem duoc)")
print("=" * 70)
print("\n  Web Server dang chay tren Cong 5173... Vui long KHONG tat cua so nay!\n")

# Auto open browser
try:
    webbrowser.open(f"http://localhost:{PORT}/")
except Exception:
    pass

socketserver.TCPServer.allow_reuse_address = True
try:
    with socketserver.TCPServer(('0.0.0.0', PORT), CustomHTTPHandler) as httpd:
        httpd.serve_forever()
except KeyboardInterrupt:
    print("\nWeb Server da dung.")
except Exception as e:
    print(f"\nLoi khoi chay server: {e}")
