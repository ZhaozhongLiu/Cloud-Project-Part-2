from flask import Flask, request, render_template, make_response
import os
from google.cloud import storage
import threading
import time
from btpeer import BTPeer
import base64
from datetime import datetime, timezone
from collections import defaultdict
from bt_utils import init_dht, direct_router_factory, request_ml, request_iot, bc_store, bc_fetch, find_peer_for_service
import json
import uuid
import socket
import random
from handlers import ml_handlers, iot_handlers

app = Flask(__name__)
BUCKET_NAME = "drum-videos"

def get_available_port(max_port=20000, attempts=100):
    for _ in range(attempts):
        port = random.randint(1024, max_port)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('', port))
                s.listen(1)
                print(f"[DEBUG] Allocated port: {port}")
                return port
            except OSError:
                continue
    raise RuntimeError(f"Could not find a free port under {max_port} after {attempts} attempts.")

# --------------------- Utility to combine ML + IOT --------------------

def combine_and_analyze(iot_data, ml_data):
    combined_result = {}

    # Infer base time from FIRST IoT timestamp
    if not iot_data:
        print("No IoT data to analyze.")
        return {}

    try:
        first_ts = datetime.fromisoformat(iot_data[0]["timestamp"].replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception as e:
        print(f"Failed to parse first IoT timestamp: {e}")
        return {}

    #Group IoT data by second offset from first timestamp
    iot_per_second = defaultdict(lambda: {"volume": [], "vibration": []})

    for entry in iot_data:
        try:
            ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")).astimezone(timezone.utc)
            second_offset = int((ts - first_ts).total_seconds())
            iot_per_second[second_offset]["volume"].append(entry["room_noise (db)"])
            iot_per_second[second_offset]["vibration"].append(entry["vibration_level"])
        except Exception as e:
            print(f"Skipping malformed timestamp: {entry['timestamp']} ({e})")

    # Use ML seconds as baseline
    ml_per_second = ml_data.get("per_second_hits", {})
    ml_seconds = sorted(int(s) for s in ml_per_second)

    for sec in ml_seconds:
        hits = ml_per_second.get(str(sec), {})
        volume_list = iot_per_second.get(sec, {}).get("volume", [])
        vibration_list = iot_per_second.get(sec, {}).get("vibration", [])

        avg_volume = sum(volume_list) / len(volume_list) if volume_list else None
        avg_vibration = sum(vibration_list) / len(vibration_list) if vibration_list else None

        warning = None
        if (avg_volume and avg_volume > 70) or (avg_vibration and avg_vibration > 70):
            warn_parts = []
            if avg_volume and avg_volume > 70:
                warn_parts.append(f"Volume ({avg_volume:.1f}db)")
            if avg_vibration and avg_vibration > 70:
                warn_parts.append(f"Vibration ({avg_vibration:.1f})")
            warning = "Warning: " + " and ".join(warn_parts)
            if hits:
                most_hit = max(hits.items(), key=lambda x: x[1])[0]
                warning += f", you were hitting '{most_hit}' the most."

        combined_result[sec] = {
            "volume": avg_volume,
            "vibration": avg_vibration,
            "hits": hits,
            "warning": warning
        }

    return combined_result

def start_peer(start_time, end_time, video_path, result_id):
    peer_port = get_available_port()
    peer_type = random.choice(["BC", "IOT", "ML"])
    peer = BTPeer(maxpeers=5, serverport=peer_port, peertype=peer_type)

    # Initialize Kademlia DHT and router
    kad, loop = init_dht(peer)
    peer.add_router(direct_router_factory(peer, kad, loop))

    if peer.peertype == "BC":
        from handlers import bc_handlers as _bc
        peer.add_handler("BCRQ", lambda conn, msg: _bc.bc_request_handler(peer, conn, msg))
        peer.add_handler("BCRS", lambda conn, msg: _bc.bc_response_handler(peer, msg))

    if peer.peertype == "IOT":
        peer.add_handler("IORQ", lambda conn, msgdata: iot_handlers.iot_request_handler(peer, conn, msgdata))
        threading.Thread(target=iot_handlers.start_aws_iot_listener, daemon=True).start()

    if peer.peertype == "ML":
        peer.add_handler("MLRQ", lambda conn, msgdata: ml_handlers.ml_request_handler(peer, conn, msgdata))

    def run():
        t = threading.Thread(target=peer.mainloop, daemon=True)
        t.start()

        # Upload video to GCS
        # video_url = upload_video_to_bucket(BUCKET_NAME, video_path)

        # --- Request ML ---
        try:
            ml_data = request_ml(peer, kad, loop, BUCKET_NAME, video_path)
            print("[WEB PEER] ML Results:", ml_data)
        except Exception as e:
            print(f"[WEB PEER] ML request failed: {e}")
            return

        # --- Request IoT ---
        try:
            iot_data = request_iot(peer, kad, loop, start_time, end_time)
            print("[WEB PEER] IoT Results:", iot_data)
        except Exception as e:
            print(f"[WEB PEER] IoT request failed: {e}")
            return

        # --- Combine and Analyze ---
        if ml_data and iot_data:
            combined_data = combine_and_analyze(iot_data, ml_data)

            os.makedirs("results", exist_ok=True)
            with open(f"results/{result_id}.json", "w") as f:
                json.dump(combined_data, f, indent=2)
            print(f"Combined results saved to results/{result_id}.json")

            # --- Store in Blockchain ---
            try:
                bc_result = bc_store(peer, kad, loop, combined_data)
                print("[WEB PEER] Blockchain response:", bc_result)
            except Exception as e:
                print(f"[WEB PEER] Blockchain store failed: {e}")

            try:
                bc_chain = bc_fetch(peer, kad, loop)
                print("[WEB PEER] Blockchain fetch:", bc_chain)
            except Exception as e:
                print(f"[WEB PEER] Blockchain fetch failed: {e}")

        peer.shutdown = True
        loop.call_soon_threadsafe(loop.stop)

    threading.Thread(target=run).start()

# --------------------- Web Routes --------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/submit", methods=["POST"])
def submit():
    start_time = request.form.get("start_time")
    end_time = request.form.get("end_time")
    video = request.files.get("video")

    if not (start_time and end_time and video):
        return "Missing fields", 400

    save_path = os.path.join("uploads", video.filename)
    os.makedirs("uploads", exist_ok=True)
    video.save(save_path)

    result_id = str(uuid.uuid4())
    start_peer(start_time, end_time, save_path, result_id)

    resp = make_response(render_template("submitted.html"))
    resp.set_cookie("result_id", result_id)
    return resp

@app.route("/results")
def results():
    result_id = request.cookies.get("result_id")
    if not result_id:
        return "No result ID found. Please upload a session first."

    result_path = f"results/{result_id}.json"
    if not os.path.exists(result_path):
        return "Results not ready yet. Please wait and refresh."

    with open(result_path, "r") as f:
        combined_data = json.load(f)

    return render_template("results.html", results=combined_data)

if __name__ == "__main__":
    app.run(debug=True)
