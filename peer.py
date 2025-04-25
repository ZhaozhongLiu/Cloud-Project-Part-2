import sys
import threading
from btpeer import BTPeer, BTPeerConnection

# ---------------- handler callback ----------------
def ping_handler(conn: BTPeerConnection, msgdata: str):
    """Reply with PONG when receiving PING."""
    sender_id = msgdata or conn.id
    if conn.id is None:
        conn.id = sender_id            # cache the sender's identity
    print(f"[{peer.myid}] got PING from {sender_id}")
    conn.senddata("PONG", peer.myid)   # respond with my identity

def pong_handler(conn: BTPeerConnection, msgdata: str):
    sender_id = msgdata or conn.id
    print(f"[{peer.myid}] got PONG from {sender_id}")

# ---------------- create peer ----------------
if len(sys.argv) != 3:
    print("Usage: python peer.py <port> <maxpeers>")
    sys.exit(1)

port, maxpeers = map(int, sys.argv[1:3])
peer = BTPeer(maxpeers=maxpeers, serverport=port)

# Direct router function and registration
def direct_router(pid: str):
    try:
        host, port = peer.get_peer(pid)
        return (pid, host, port)
    except KeyError:
        return (None, None, None)

peer.add_router(direct_router)

peer.add_handler("PING", ping_handler)
peer.add_handler("PONG", pong_handler)

# Optional: Periodically print the list of live peers
def heartbeat():
    peer.check_live_peers()
    print(f"### [{peer.myid}] known peers:", peer.get_peer_ids())

#peer.start_stabilizer(heartbeat, delay=120)  # Run every 10 seconds

# ---------------- Run mainloop in background thread ----------------
t = threading.Thread(target=peer.mainloop, daemon=True)
t.start()

# ---------------- Simple CLI ----------------
while True:
    cmd = input("cmd> ").strip().split()
    if not cmd:
        continue
    if cmd[0] == "add" and len(cmd) == 4:
        _, pid, host, p = cmd
        peer.add_peer(pid, host, int(p))
    elif cmd[0] == "ping" and len(cmd) == 2:
        peer.send_to_peer(cmd[1], "PING", peer.myid, waitreply=True)
    elif cmd[0] == "list":
        print(peer.get_peer_ids())
    elif cmd[0] == "quit":
        peer.shutdown = True
        break
    elif cmd[0] == "heartbeat":
        peer.check_live_peers()
        print(f"### [{peer.myid}] known peers:", peer.get_peer_ids()) 
    else:
        print("Commands: add <peerid> <host> <port> | ping <peerid> | list | quit")