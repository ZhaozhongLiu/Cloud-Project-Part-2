import sys
import threading
from btpeer import BTPeer, BTPeerConnection
from handlers import ml_handlers, iot_handlers, bc_handlers
import base64

from google.cloud import storage
import os

# ---------------- create peer ----------------
if len(sys.argv) != 4:
    print("Usage: python peer.py <port> <maxpeers> <peertype>")
    sys.exit(1)

port, maxpeers, peertype = sys.argv[1], sys.argv[2], sys.argv[3]
peer = BTPeer(maxpeers=int(maxpeers), serverport=int(port), peertype=peertype.upper())

# Direct router function and registration
def direct_router(pid: str):
    try:
        host, port, peertype = peer.get_peer(pid)
        return (pid, host, port)
    except KeyError:
        return (None, None, None)

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
def get_peer_by_service(service_type):
    for pid, (host, port, ptype) in peer.peers.items():
        if ptype == service_type.upper():
            return pid
    return None

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
    if cmd[0] == "add" and len(cmd) == 5:
        _, pid, host, p, ptype = cmd
        peer.add_peer(pid, host, int(p), ptype)
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

        target_peer = get_peer_by_service("ML")
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
        target_peer = get_peer_by_service("IOT")
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
        target_peer = get_peer_by_service("BC")
        if target_peer:
            print(f"Sending Blockchain request to {target_peer}")
            peer.send_to_peer(target_peer, "BCRQ", "example-bc-data", waitreply=True)
        else:
            print("No known Blockchain peer found.")
    else:
        print("Commands: add <peerid> <host> <port> <peertype> | ping <peerid> | list | quit")