import subprocess
import time
import os

# Start ML Node
print("[Starter] Starting ML Node on port 6000...")
ml_node = subprocess.Popen(
    [os.path.join(".venv", "Scripts", "python.exe"), "peer.py", "6000", "10", "ML"],
    stdin=subprocess.PIPE
)

time.sleep(3)

# Start IOT Node
print("[Starter] Starting IOT Node on port 6001...")
iot_node = subprocess.Popen(
    [os.path.join(".venv", "Scripts", "python.exe"), "peer.py", "6001", "10", "IOT"],
    stdin=subprocess.PIPE
)

time.sleep(3)

# Register peers (send "add" command to running peers)
print("[Starter] Registering peers...")

ml_node.stdin.write(b"add IOTNode localhost 6001 IOT\n")
ml_node.stdin.flush()

iot_node.stdin.write(b"add MLNode localhost 6000 ML\n")
iot_node.stdin.flush()

print("[Starter] Peers registered. System ready.")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("[Starter] Shutting down...")
    ml_node.terminate()
    iot_node.terminate()
