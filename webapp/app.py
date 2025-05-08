from flask import Flask, request, render_template
import os
from google.cloud import storage
import threading
import time
from btpeer import BTPeer
import base64

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

        for msgtype, msgdata in ml_replies:
            if msgtype == "MLRS":
                print("[WEB PEER] ML Results:", msgdata)

        # IoT Request
        time_range = f"{start_time}|{end_time}"
        print("[WEB PEER] Sending IoT request...")
        iot_replies = peer.send_to_peer("Test", "IORQ", time_range, waitreply=True)

        for msgtype, msgdata in iot_replies:
            if msgtype == "IORS":
                print("[WEB PEER] IoT Results:", msgdata)

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

    return "Request sent to ML and IoT peers!"

if __name__ == "__main__":
    app.run(debug=True)
