import sys
import threading
from btpeer import BTPeer, BTPeerConnection
from handlers import ml_handlers, iot_handlers, bc_handlers
import base64
import time
import logging
# log = logging.getLogger("kademlia")
# log.setLevel(logging.DEBUG)
# log.addHandler(logging.StreamHandler())

import asyncio, json
from kademlia.network import Server as KadServer


from google.cloud import storage
import os

BOOTSTRAP_NODE = ("127.0.0.1", 7000)

# ---------------- create peer ----------------
if len(sys.argv) != 4:
    print("Usage: python peer.py <port> <maxpeers> <peertype>")
    sys.exit(1)

port, maxpeers, peertype = sys.argv[1], sys.argv[2], sys.argv[3]
peer = BTPeer(maxpeers=int(maxpeers), serverport=int(port), peertype=peertype.upper())

# --------------- Kademlia setup ---------------
# run the Kademlia node on port = your peer port + 10000 (or any free port)
KAD_PORT = peer.serverport + 10000
kad_loop = asyncio.new_event_loop()
asyncio.set_event_loop(kad_loop)

kad = KadServer()

async def start_kademlia():
    await kad.listen(KAD_PORT)
    # bootstrap from any known peer (you can use your static peers for now)
    # format: ("host", kad_port)
    bootstrap_nodes = [(BOOTSTRAP_NODE[0], BOOTSTRAP_NODE[1] + 10000)]
    if (peer.serverhost, peer.serverport) != BOOTSTRAP_NODE:
        await kad.bootstrap([(BOOTSTRAP_NODE[0], BOOTSTRAP_NODE[1] + 10000)])
    await kad.set(peer.myid, json.dumps({
        "host": peer.serverhost,
        "port": peer.serverport,
        "type": peer.peertype,
    }))

def announce_service(pid, ptype):
    """
    Fetch the current list under "svc:<ptype>", append pid if missing, and re-store.
    """
    key = f"svc:{ptype.upper()}"
    async def _update():
        # fetch existing (might be None or JSON list)
        raw = await kad.get(key)
        lst = json.loads(raw) if raw else []
        if pid not in lst:
            lst.append(pid)
            await kad.set(key, json.dumps(lst))
    asyncio.run_coroutine_threadsafe(_update(), kad_loop)
def add_and_announce(pid, host, port, ptype):
    # 1) add into your BT peer table
    peer.add_peer(pid, host, port, ptype)

    # 2) tell the DHT about them
    info = json.dumps({"host": host, "port": port, "type": ptype})
    asyncio.run_coroutine_threadsafe(kad.set(pid, info), kad_loop)

    # 3) bootstrap off of them so they enter your routing table
    bootstrap_node = (host, port + 10000)
    asyncio.run_coroutine_threadsafe(kad.bootstrap([bootstrap_node]), kad_loop)
    announce_service(pid, ptype)

# start it in the background
kad_loop.run_until_complete(start_kademlia())
threading.Thread(target=kad_loop.run_forever, daemon=True).start()
time.sleep(0.5)
# retry bootstrap now that everyone’s listening
if (peer.serverhost, peer.serverport) != BOOTSTRAP_NODE:
    asyncio.run_coroutine_threadsafe(
      kad.bootstrap([ (BOOTSTRAP_NODE[0], BOOTSTRAP_NODE[1]+10000) ]),
      kad_loop
    )
announce_service(peer.myid, peer.peertype)
# ------------------------------------------------



# Direct router function and registration
# def direct_router(pid: str):
#     try:
#         host, port, peertype = peer.get_peer(pid)
#         return (pid, host, port)
#     except KeyError:
#         return (None, None, None)

def direct_router(pid: str):
    # first, try local cache:
    if pid in peer.peers:
        h, p, t = peer.peers[pid]
        return (pid, h, p)

    # else, ask the DHT
    future = asyncio.run_coroutine_threadsafe(kad.get(pid), kad_loop)
    try:
        raw = future.result(timeout=5)   # wait up to 5s
    except Exception:
        return (None, None, None)

    if not raw:
        return (None, None, None)

    data = json.loads(raw)
    # cache it locally for next time
    peer.add_peer(pid, data["host"], data["port"], data["type"])
    return (pid, data["host"], data["port"])

peer.add_router(direct_router)

if peer.peertype == "IOT":
    peer.add_handler("IORQ", lambda conn, msgdata: iot_handlers.iot_request_handler(peer, conn, msgdata))
    threading.Thread(target=iot_handlers.start_aws_iot_listener, daemon=True).start()

if peer.peertype == "ML":
    peer.add_handler("MLRQ", lambda conn, msgdata: ml_handlers.ml_request_handler(peer, conn, msgdata))

# Optional: Periodically print the list of live peers
def heartbeat():
    peer.check_live_peers()
    print(f"### [{peer.myid}] known peers:", peer.get_peer_ids())

#peer.start_stabilizer(heartbeat, delay=120)  # Run every 10 seconds

# ---------------- Run mainloop in background thread ----------------
t = threading.Thread(target=peer.mainloop, daemon=True)
t.start()

# ---------------- Simple CLI ----------------
# def get_peer_by_service(service_type):
#     for pid, (host, port, ptype) in peer.peers.items():
#         if ptype == service_type.upper():
#             return pid
#     return None

def find_peer_for_service(service_type: str, timeout=5):
    # 1) fetch the list of IDs for that service
    key = f"svc:{service_type.upper()}"
    future = asyncio.run_coroutine_threadsafe(kad.get(key), kad_loop)
    try:
        raw = future.result(timeout=timeout)
    except Exception:
        return None

    if not raw:
        return None
    ids = json.loads(raw)
    if not ids:
        return None

    # 2) pick one at random (or first)
    target_id = ids[0]

    # 3) resolve its contact info via your DHT-backed direct_router
    pid, host, port = direct_router(target_id)
    if pid is None:
        return None
    return pid


def upload_video_to_bucket(bucket_name, source_file_path):
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob_name = os.path.basename(source_file_path)
    blob = bucket.blob(blob_name)

    blob.upload_from_filename(source_file_path)

    # Make public
    blob.make_public()

    print(f"Uploaded to {blob.public_url}")
    return blob.public_url
def delete_from_gcs(bucket_name, blob_name):
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    blob.delete()

    print(f"Deleted {blob_name} from {bucket_name}")

while True:
    cmd = input("cmd> ").strip().split()
    if not cmd:
        continue
    # if cmd[0] == "add" and len(cmd) == 5:
    #     _, pid, host, p, ptype = cmd
    #     peer.add_peer(pid, host, int(p), ptype)
    if cmd[0] == "add" and len(cmd) == 5:
        _, pid, host, p, ptype = cmd
        # Instead of peer.add_peer, use our helper
        add_and_announce(pid, host, int(p), ptype)
        print(f"Added {pid}@{host}:{p} [{ptype}] and stored in DHT")

    elif cmd[0] == "ping" and len(cmd) == 2:
        replies = peer.send_to_peer(cmd[1], "PING", peer.myid, waitreply=True)
        # print("Replies:", replies)
    elif cmd[0] == "list":
        for pid, (host, port, ptype) in peer.peers.items():
            print(f"{pid} @ {host}:{port} [{ptype}]")
    elif cmd[0] == "quit":
        peer.shutdown = True
        break
    elif cmd[0] == "heartbeat":
        peer.check_live_peers()
        print(f"### [{peer.myid}] known peers:", peer.get_peer_ids())

    elif cmd[0] == "request_ml":

        # target_peer = get_peer_by_service("ML")
        target_peer = find_peer_for_service("ML")
        if not target_peer:
            print("No known ML peer found.")
            continue
        if len(cmd) == 2:
            video_path = cmd[1]
            # Upload video
            try:
                video_url = upload_video_to_bucket("drum-videos", video_path)
            except FileNotFoundError as e:
                print(f"Failed to upload video: {e}")
                continue

            data_to_send = video_url
            print(f"Sending video ML request to {target_peer}: {video_url}")

        else:
            data_to_send = "example-ml-data"
            print(f"Sending simple ML request to {target_peer}")

        replies = peer.send_to_peer(target_peer, "MLRQ", data_to_send, waitreply=True)

        for msgtype, msgdata in replies:
            if msgtype == "MLRS":
                ml_handlers.ml_response_handler(peer, msgdata)
                # Delete from GCS using just the filename
                delete_from_gcs("drum-videos", os.path.basename(video_path))
            else:
                print(f"Unknown reply type: {msgtype}")

    elif cmd[0] == "request_iot" and len(cmd) == 3:
        # target_peer = get_peer_by_service("IOT")
        target_peer = find_peer_for_service("IOT")
        if target_peer:
            time_range = f"{cmd[1]}|{cmd[2]}"
            print(f"Requesting IoT data from {target_peer} for {time_range}")
            replies = peer.send_to_peer(target_peer, "IORQ", time_range, waitreply=True)
            for msgtype, msgdata in replies:
                if msgtype == "IORS":
                    iot_handlers.iot_response_handler(peer, msgdata)
                else:
                    print(f"Unknown reply type: {msgtype}")
        else:
            print("No known IoT peer found.")

    elif cmd[0] == "request_bc":
        # target_peer = get_peer_by_service("BC")
        target_peer = find_peer_for_service("BC")
        if target_peer:
            print(f"Sending Blockchain request to {target_peer}")
            peer.send_to_peer(target_peer, "BCRQ", "example-bc-data", waitreply=True)
        else:
            print("No known Blockchain peer found.")
    else:
        print("Commands: add <peerid> <host> <port> <peertype> | ping <peerid> | list | quit")