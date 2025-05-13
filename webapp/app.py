from flask import Flask, request, render_template
import os
from google.cloud import storage
import threading
import time
from btpeer import BTPeer
import base64
from datetime import datetime, timezone
from collections import defaultdict
import json

app = Flask(__name__)
BUCKET_NAME = "drum-videos"

# --------------------- Upload to GCS --------------------
def upload_video_to_bucket(bucket_name, source_file_path):
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob_name = os.path.basename(source_file_path)
    blob = bucket.blob(blob_name)

    blob.upload_from_filename(source_file_path)
    blob.make_public()

    return blob.public_url

# --------------------- Utility to combine ML + IOT --------------------
from datetime import datetime, timezone
from collections import defaultdict

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

    #Step 2: Use ML seconds as baseline
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



# --------------------- Peer Client --------------------
def start_peer(start_time, end_time, video_path):
    peer = BTPeer(maxpeers=5, serverport=0, peertype="WEB")  # random port
    peer.add_router(lambda pid: (pid, "localhost", 6000 if pid == "MLNode" else 6001))

    def run():
        t = threading.Thread(target=peer.mainloop, daemon=True)
        t.start()

        # Upload video
        video_url = upload_video_to_bucket(BUCKET_NAME, video_path)

        # ML Request
        print("[WEB PEER] Sending ML request...")
        ml_replies = peer.send_to_peer("MLNode", "MLRQ", video_url, waitreply=True)
        ml_data = None
        for msgtype, msgdata in ml_replies:
            if msgtype == "MLRS":
                print("[WEB PEER] ML Results:", msgdata)
                ml_data = json.loads(msgdata)

        # IoT Request
        time_range = f"{start_time}|{end_time}"
        print("[WEB PEER] Sending IoT request...")
        iot_replies = peer.send_to_peer("Test", "IORQ", time_range, waitreply=True)
        iot_data = None
        for msgtype, msgdata in iot_replies:
            if msgtype == "IORS":
                print("[WEB PEER] IoT Results:", msgdata)
                iot_data = json.loads(msgdata)

        if ml_data and iot_data:
            combined_data = combine_and_analyze(iot_data, ml_data)

            with open("combined_results.json", "w") as f:
                json.dump(combined_data, f, indent=2)
            print("Combined results saved to combined_results.json")
        peer.shutdown = True

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

    # Start peer client
    start_peer(start_time, end_time, save_path)

    return "Request sent to ML and IoT peers! <a href='/results'>Check Results</a> (refresh this page in a moment)"

@app.route("/results")
def results():
    if not os.path.exists("combined_results.json"):
        return "Results not ready yet. Please wait and refresh."

    with open("combined_results.json", "r") as f:
        combined_data = json.load(f)

    return render_template("results.html", results=combined_data)

if __name__ == "__main__":
    app.run(debug=True)
