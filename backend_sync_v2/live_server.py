"""
LIVE SERVER V2 -- WebSocket Realtime Broadcast Server (Host: 0.0.0.0, Port 8088)
Broadcasts real-time KPI and update events to all connected Web clients across LAN & Localhost.
"""

import sys
import os
import json
import asyncio
import websockets
import datetime

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
LAST_UPDATE_PATH = os.path.join(ROOT_DIR, "public", "data", "last_update.json")

CLIENTS = set()

async def register(websocket):
    CLIENTS.add(websocket)
    print(f"🟢 [LIVE SERVER V2] Client connected from {websocket.remote_address} (Total: {len(CLIENTS)})")
    try:
        # Send current last_update.json immediately on connect
        if os.path.exists(LAST_UPDATE_PATH):
            with open(LAST_UPDATE_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            await websocket.send(json.dumps({"type": "REALTIME_UPDATE", "data": data}))
    except Exception as e:
        print(f"⚠️ Error sending initial frame: {e}")

async def unregister(websocket):
    CLIENTS.remove(websocket)
    print(f"🔴 [LIVE SERVER V2] Client disconnected (Remaining: {len(CLIENTS)})")

async def handler(websocket, path=None):
    await register(websocket)
    try:
        async for message in websocket:
            if message == "ping":
                await websocket.send(json.dumps({"type": "pong", "time": datetime.datetime.now().strftime("%H:%M:%S")}))
    except websockets.ConnectionClosedError:
        pass
    finally:
        await unregister(websocket)

async def broadcast_loop():
    last_mtime = 0
    while True:
        try:
            if os.path.exists(LAST_UPDATE_PATH):
                mtime = os.path.getmtime(LAST_UPDATE_PATH)
                if mtime > last_mtime:
                    last_mtime = mtime
                    with open(LAST_UPDATE_PATH, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    if CLIENTS:
                        payload = json.dumps({"type": "REALTIME_UPDATE", "data": data})
                        await asyncio.gather(*[client.send(payload) for client in CLIENTS if client.open], return_exceptions=True)
                        print(f"📡 [LIVE SERVER V2] Broadcasted update to {len(CLIENTS)} clients at {datetime.datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"⚠️ Broadcast loop error: {e}")
            
        await asyncio.sleep(2)

async def main():
    host = "0.0.0.0"
    port = 8088
    print(f"🚀 [LIVE SERVER V2] WebSocket Broadcast Server starting on ws://0.0.0.0:{port} (Accessible via Localhost & LAN)...")
    
    server = await websockets.serve(handler, host, port)
    await asyncio.gather(server.wait_closed(), broadcast_loop())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Live Server V2 stopped.")
