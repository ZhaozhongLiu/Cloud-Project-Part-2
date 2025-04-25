# peer.py
import sys
import threading
from btpeer import BTPeer, BTPeerConnection

# ---------------- handler 回调 ----------------
def ping_handler(conn: BTPeerConnection, _):
    """收到 PING 就回 PONG"""
    print(f"[{peer.myid}] got PING from {conn.id}")
    conn.senddata("PONG", "")

def pong_handler(_, __):
    print(f"[{peer.myid}] got PONG")

# ---------------- 创建 peer ----------------
if len(sys.argv) != 3:
    print("用法: python peer.py <port> <maxpeers>")
    sys.exit(1)

port, maxpeers = map(int, sys.argv[1:3])
peer = BTPeer(maxpeers=maxpeers, serverport=port)

peer.add_handler("PING", ping_handler)
peer.add_handler("PONG", pong_handler)

# 可选：定时打印存活 peer 列表
def heartbeat():
    peer.check_live_peers()
    print(f"### [{peer.myid}] known peers:", peer.get_peer_ids())

peer.start_stabilizer(heartbeat, delay=10)  # 每 10 秒跑一次

# ---------------- 背景线程跑 mainloop ----------------
t = threading.Thread(target=peer.mainloop, daemon=True)
t.start()

# ---------------- 简易 CLI ----------------
while True:
    cmd = input("cmd> ").strip().split()
    if not cmd:
        continue
    if cmd[0] == "add" and len(cmd) == 4:
        _, pid, host, p = cmd
        peer.add_peer(pid, host, int(p))
    elif cmd[0] == "ping" and len(cmd) == 2:
        peer.send_to_peer(cmd[1], "PING", "", waitreply=True)
    elif cmd[0] == "list":
        print(peer.get_peer_ids())
    elif cmd[0] == "quit":
        peer.shutdown = True
        break
    else:
        print("命令: add <peerid> <host> <port> | ping <peerid> | list | quit")