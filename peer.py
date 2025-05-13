# #!/usr/bin/env python3
# """
# peer.py – P2P Entrypoint (BC / ML / IoT Nodes)
# --------------------------------------------
# This script serves as the entry point for a peer-to-peer network, allowing
# different types of nodes (Blockchain, Machine Learning, IoT) to communicate
# and share data. It includes a command-line interface for basic operations
# such as adding peers, pinging, and sending requests. The script also
# handles the registration of different message types and their corresponding
# handlers based on the node type.
#
# Usage:
#     python peer.py <port> <maxpeers> <peertype>
#     where <peertype> can be BC, ML, or IOT.
#     <port> is the port number for the peer-to-peer server.
#     <maxpeers> is the maximum number of peers to connect to.
#     <peertype> is the type of peer (BC, ML, or IOT).
# """
#
# import sys
# import threading
# import json
# import os
# from btpeer import BTPeer, BTPeerConnection
# from handlers import ml_handlers, iot_handlers  # ML/IoT handlers (lazy-loaded)
# from google.cloud import storage
#
# # ---------------- Instantiate peer ----------------
# if len(sys.argv) != 4:
#     print("Usage: python peer.py <port> <maxpeers> <peertype>")
#     sys.exit(1)
#
# port, maxpeers, peertype = sys.argv[1], sys.argv[2], sys.argv[3]
# peertype = peertype.upper()
#
# peer = BTPeer(maxpeers=int(maxpeers), serverport=int(port), peertype=peertype)
# peer.add_peer(peer.myid, peer.serverhost, int(port), peertype)
#
# # ---------------- Router function ----------------
# def direct_router(pid: str):
#     try:
#         host, port, _ptype = peer.get_peer(pid)
#         return (pid, host, port)
#     except KeyError:
#         return (None, None, None)
#
# peer.add_router(direct_router)
#
# # ---------------- Register handlers by node type ----------------
# if peer.peertype == "BC":
#     # Lazy-load blockchain handler to avoid web3 dependency for other nodes
#     from handlers import bc_handlers as _bc
#
#     peer.add_handler("BCRQ", lambda conn, msg: _bc.bc_request_handler(peer, conn, msg))
#     peer.add_handler("BCRS", lambda conn, msg: _bc.bc_response_handler(peer, msg))
#
# if peer.peertype == "IOT":
#     from handlers import iot_handlers  # Lazy-load IoT handler
#
#     peer.add_handler(
#         "IORQ",
#         lambda conn, msgdata: iot_handlers.iot_request_handler(peer, conn, msgdata),
#     )
#     threading.Thread(target=iot_handlers.start_aws_iot_listener, daemon=True).start()
#
# if peer.peertype == "ML":
#     from handlers import ml_handlers  # Lazy-load ML handler
#
#     peer.add_handler(
#         "MLRQ",
#         lambda conn, msgdata: ml_handlers.ml_request_handler(peer, conn, msgdata),
#     )
#
# # ---------------- Start main loop ----------------
# threading.Thread(target=peer.mainloop, daemon=True).start()
#
# # ---------------- Utility functions ----------------
# def get_peer_by_service(service_type: str) -> str | None:
#     """Return the first peer ID matching the given service type."""
#     for pid, (_h, _p, ptype) in peer.peers.items():
#         if ptype == service_type.upper():
#             return pid
#     return None
#
# # Example GCS upload/delete tools (used by ML handler)
# def upload_video_to_bucket(bucket_name: str, source_file_path: str) -> str:
#     """Upload a file to GCS and make it public."""
#     storage_client = storage.Client()
#     bucket = storage_client.bucket(bucket_name)
#     blob = bucket.blob(os.path.basename(source_file_path))
#     blob.upload_from_filename(source_file_path)
#     blob.make_public()
#     url = blob.public_url
#     print(f"Uploaded to {url}")
#     return url
#
#
# def delete_from_gcs(bucket_name: str, blob_name: str) -> None:
#     """Delete a blob from GCS."""
#     storage_client = storage.Client()
#     bucket = storage_client.bucket(bucket_name)
#     bucket.blob(blob_name).delete()
#     print(f"Deleted {blob_name} from {bucket_name}")
#
# # ---------------- Simple CLI ----------------
# HELP = """
# Commands
# ========
# add <peerid> <host> <port> <peertype>
# list                             # Show known peers
# ping <peerid>                    # Ping a peer
# heartbeat                        # Check live peers
# quit
#
# Blockchain
# ----------
# bc_store <text|JSON>             # Store data on-chain
# bc_fetch                         # Fetch all on-chain data
#
# ML / IoT Examples
# -----------------
# request_ml  <local_video_path>
# request_iot <start_iso> <end_iso>
# """
# print(HELP)
#
# while True:
#     try:
#         parts = input("cmd> ").strip().split(maxsplit=1)
#     except (EOFError, KeyboardInterrupt):
#         break
#
#     if not parts:
#         continue
#     op = parts[0].lower()
#
#     # ---- Basic P2P commands ----
#     if op == "add":
#         try:
#             pid, host, p, ptype = parts[1].split()
#             peer.add_peer(pid, host, int(p), ptype)
#         except Exception:
#             print("Usage: add <peerid> <host> <port> <peertype>")
#
#     elif op == "ping" and len(parts) == 2:
#         print(peer.send_to_peer(parts[1], "PING", peer.myid, waitreply=True))
#
#     elif op == "list":
#         for pid, (h, p, t) in peer.peers.items():
#             print(f"{pid:<10} {h}:{p:<5} [{t}]")
#
#     elif op == "heartbeat":
#         peer.check_live_peers()
#         print("Live peers:", peer.get_peer_ids())
#
#     elif op == "quit":
#         peer.shutdown = True
#         break
#
#     # ---- Blockchain ----
#     elif op == "bc_store":
#         if len(parts) == 1:
#             print("Usage: bc_store <text|JSON>")
#             continue
#         payload = parts[1]
#         target = get_peer_by_service("BC") or peer.myid
#         replies = peer.send_to_peer(target, "BCRQ", f"STORE {payload}", waitreply=True)
#         for msg_type, msg_data in replies:
#             if msg_type == "BCRS":
#                 from handlers import bc_handlers as _bc
#                 _bc.bc_response_handler(peer, msg_data)
#
#     elif op == "bc_fetch":
#         target = get_peer_by_service("BC") or peer.myid
#         replies = peer.send_to_peer(target, "BCRQ", "FETCH", waitreply=True)
#         for msg_type, msg_data in replies:
#             if msg_type == "BCRS":
#                 from handlers import bc_handlers as _bc
#                 _bc.bc_response_handler(peer, msg_data)
#
#     # ---- ML example ----
#     elif op[0] == "request_ml":
#
#         target_peer = get_peer_by_service("ML")
#         if not target_peer:
#             print("No known ML peer found.")
#             continue
#         if len(op) == 2:
#             video_path = op[1]
#             # Upload video
#             try:
#                 video_url = upload_video_to_bucket("drum-videos", video_path)
#             except FileNotFoundError as e:
#                 print(f"Failed to upload video: {e}")
#                 continue
#
#             data_to_send = video_url
#             print(f"Sending video ML request to {target_peer}: {video_url}")
#
#         else:
#             data_to_send = "example-ml-data"
#             print(f"Sending simple ML request to {target_peer}")
#
#         replies = peer.send_to_peer(target_peer, "MLRQ", data_to_send, waitreply=True)
#
#         for msgtype, msgdata in replies:
#             if msgtype == "MLRS":
#                 ml_handlers.ml_response_handler(peer, msgdata)
#                 # Delete from GCS using just the filename
#                 delete_from_gcs("drum-videos", os.path.basename(video_path))
#             else:
#                 print(f"Unknown reply type: {msgtype}")
#
#
#     # ---- IoT example ----
#     elif op[0] == "request_iot" and len(op) == 3:
#         target_peer = get_peer_by_service("IOT")
#         if target_peer:
#             time_range = f"{op[1]}|{op[2]}"
#             print(f"Requesting IoT data from {target_peer} for {time_range}")
#             replies = peer.send_to_peer(target_peer, "IORQ", time_range, waitreply=True)
#             for msgtype, msgdata in replies:
#                 if msgtype == "IORS":
#                     iot_handlers.iot_response_handler(peer, msgdata)
#                 else:
#                     print(f"Unknown reply type: {msgtype}")
#         else:
#             print("No known IoT peer found.")
#
#     elif op == "help":
#         print(HELP)
#     else:
#         print("Unknown command. Type 'help' for available commands.")


import sys
import threading
from btpeer import BTPeer, BTPeerConnection
from handlers import ml_handlers, iot_handlers
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

if peer.peertype == "BC":
    from handlers import bc_handlers as _bc
    peer.add_handler("BCRQ", lambda conn, msg: _bc.bc_request_handler(peer, conn, msg))
    peer.add_handler("BCRS", lambda conn, msg: _bc.bc_response_handler(peer, msg))

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

    # ---- Blockchain ----
    elif cmd[0] == "bc_store" and len(cmd) == 2:
        payload = cmd[1]
        target = get_peer_by_service("BC") or peer.myid
        replies = peer.send_to_peer(target, "BCRQ", f"STORE {payload}", waitreply=True)
        for msg_type, msg_data in replies:
            if msg_type == "BCRS":
                from handlers import bc_handlers as _bc
                _bc.bc_response_handler(peer, msg_data)

    elif cmd[0] == "bc_fetch":
        target = get_peer_by_service("BC") or peer.myid
        replies = peer.send_to_peer(target, "BCRQ", "FETCH", waitreply=True)
        for msg_type, msg_data in replies:
            if msg_type == "BCRS":
                from handlers import bc_handlers as _bc
                _bc.bc_response_handler(peer, msg_data)
    else:
        print("Commands: add <peerid> <host> <port> <peertype> | ping <peerid> | list | quit")