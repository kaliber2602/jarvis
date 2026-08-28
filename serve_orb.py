#!/usr/bin/env python3
"""
Jarvis Orb Local Web Server:
Serves the Three.js Orb UI on localhost and runs the JarvisBridge WebSocket broker for local browser testing.
"""

import http.server
import socketserver
import webbrowser
import os
import sys
import threading

# Ensure UTF-8 output on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

PORT = 3000
UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ui')

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=UI_DIR, **kwargs)

    def log_message(self, format, *args):
        sys.stdout.write(f"[Jarvis Orb] {format % args}\n")
        sys.stdout.flush()

def run_server():
    os.chdir(UI_DIR)

    # Start JarvisBridge WebSocket broker
    try:
        from runtime_bridge import JarvisBridge
        bridge = JarvisBridge.get_instance()
        bridge.start()
    except Exception as e:
        print(f"[Jarvis Orb] Warning: Could not start JarvisBridge: {e}")

    global PORT
    httpd = None
    for attempt_port in [3000, 3001, 8000, 8080, 5000]:
        try:
            httpd = socketserver.TCPServer(("", attempt_port), Handler)
            PORT = attempt_port
            break
        except OSError:
            continue

    if httpd is None:
        print("Could not bind to any test port.")
        sys.exit(1)

    url = f"http://localhost:{PORT}"
    print("=" * 60)
    print(" JARVIS 3D REACTIVE PARTICLE ORB UI & BRIDGE DEMO")
    print(f" Web UI running at: {url}")
    print(" WebSocket Bridge: ws://127.0.0.1:8765")
    print(" Keyboard Controls:")
    print("   [1] -> HIDDEN state (Hides Orb)")
    print("   [2] -> WAKE sequence ('Jarvis, I need your help')")
    print("   [3] -> LISTENING state (live microphone)")
    print("   [4] -> PROCESSING state")
    print("   [5] -> SPEAKING state (audio reactive)")
    print("   [6] -> END SESSION (Returns to background)")
    print("   [Space] -> Trigger surface ripple pulse")
    print("   [H] -> Toggle dev status HUD")
    print("   [Drag] -> Click & drag orb with spring physics")
    print("=" * 60)
    sys.stdout.flush()

    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Jarvis Orb server.")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
