import subprocess
import sys
import time
import webbrowser
import urllib.request
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Start Flask in the same process tree
flask_proc = subprocess.Popen(
    [sys.executable, "app.py"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
)

url = "http://localhost:5000"
print("Waiting for Flask to start", end="", flush=True)

# Poll for up to 30 seconds
opened = False
for i in range(60):
    try:
        urllib.request.urlopen(url, timeout=1)
        opened = True
        break
    except Exception:
        print(".", end="", flush=True)
        time.sleep(0.5)

print()

if opened:
    print("Server ready. Opening browser...")
    webbrowser.open(url)
else:
    print("Server did not start in time. Check the window for errors.")

# Keep the process alive
try:
    flask_proc.wait()
except KeyboardInterrupt:
    print("Shutting down...")
    flask_proc.terminate()