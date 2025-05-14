import subprocess
import sys
import time
import os
import signal
import platform


# ----- Start Hardhat Node -----
def Start_Hardhat_Node()->None:
    print("[Starter] Starting Hardhat node...")
    if platform.system() == "Windows":
        # Windows: no preexec_fn; use creationflags
        npx_path = r"C:\Program Files\nodejs\npx.cmd"
        hardhat_proc = subprocess.Popen(
            [npx_path, "hardhat", "node"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        # Unix: use os.setsid
        hardhat_proc = subprocess.Popen(
            ["npx", "hardhat", "node"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid
        )


# ----- Deploy Contract -----
def Deploy_Contract()->None:
    print("[Starter] Deploying StringChain contract...")
    deploy_result = None
    if platform.system() == "Windows":
        npx_path = r"C:\Program Files\nodejs\npx.cmd"
        deploy_result = subprocess.run(
            [npx_path, "hardhat", "run", "--network", "localhost", "scripts/deploy.js"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
    else:
        deploy_result = subprocess.run(
            ["npx", "hardhat", "run", "--network", "localhost", "scripts/deploy.js"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
    print("[Starter] Deploy result:", deploy_result.stdout.decode().strip())
    time.sleep(2)


# ----- Create a BC Peer -----
def Create_BC_Peer(port: str) -> None:
    print(f"[Starter] Starting BC Node on {port}...")
    bc_node = subprocess.Popen(
        [os.path.join(".venv", "Scripts", "python"), "peer.py", port, "10", "BC"],
        stdin=subprocess.PIPE
    )
    time.sleep(3)
    return bc_node



def Create_ML_Peers(port: str):
    # Start ML Node
    print(f"[Starter] Starting ML Node on {port}...")
    ml_node = subprocess.Popen(
        [os.path.join(".venv", "Scripts", "python.exe"), "peer.py", port, "10", "ML"],
        stdin=subprocess.PIPE
    )
    time.sleep(3)
    return ml_node



def Create_IoT_Peer(port:str) :
    # Start IOT Node
    print(f"[Starter] Starting IoT Node on {port}...")
    iot_node = subprocess.Popen(
        [os.path.join(".venv", "Scripts", "python.exe"), "peer.py", port, "10", "IOT"],
        stdin=subprocess.PIPE
    )
    time.sleep(3)
    return iot_node

# Register peers (send "add" command to running peers)
print("[Starter] Registering peers...")

def Create_Bootstrap_Peer():
    print(f"[Starter] Starting Bootstrap Node... (Port 7000)")
    bootstrap_node = subprocess.Popen(
        [os.path.join(".venv", "Scripts", "python.exe"), "peer.py", "7000", "10", "Bootstrap"],
        stdin=subprocess.PIPE
    )
    time.sleep(3)
    return bootstrap_node


def main():
    python_exec = sys.executable
    if not python_exec:
        raise RuntimeError("Could not determine the current Python interpreter path.")
    print(f"Current Python interpreter: {python_exec}")

    #Star Hardhat Node and Contract
    Start_Hardhat_Node()
    Deploy_Contract()

    #Generating Peers
    bootstrap_node = Create_Bootstrap_Peer()
    bc_node = Create_BC_Peer("8001")
    iot_node = Create_IoT_Peer("6001")
    ml_node = Create_ML_Peers("6000")

    # bc_node.stdin.write(b"add BCNode localhost 8001 IOT\n")
    # bc_node.stdin.flush()
    #
    # ml_node.stdin.write(b"add IOTNode localhost 6001 IOT\n")
    # ml_node.stdin.flush()

    # iot_node.stdin.write(b"add MLNode localhost 6000 ML\n")
    # iot_node.stdin.flush()

    print("[Starter] Peers registered. System ready.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[Starter] Shutting down...")
        ml_node.terminate()
        iot_node.terminate()

main()