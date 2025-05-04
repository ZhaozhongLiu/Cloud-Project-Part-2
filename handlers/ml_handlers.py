import base64
import tempfile
import cv2
import requests
import json
from collections import defaultdict
from datetime import timedelta

def ml_request_handler(peer, conn, msgdata):
    if len(msgdata) < 1000:
        print(f"[{peer.myid}] Received simple ML request: {msgdata}")
        result = f"Processed ML Request({msgdata})"
        conn.senddata("MLRS", result)
        return

    print(f"[{peer.myid}] Received video ML request")
    video_bytes = base64.b64decode(msgdata)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
        tmp.write(video_bytes)
        tmp_path = tmp.name

    print(f"[{peer.myid}] Saved video to {tmp_path}")

    # Open video
    cap = cv2.VideoCapture(tmp_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"[{peer.myid}] Video FPS: {fps}")

    frame_number = 0
    hits_total = defaultdict(int)
    hits_per_second = defaultdict(lambda: defaultdict(int))  # {second: {drum: count}}

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_number += 1
        current_second = int(frame_number // fps)

        # Encode frame as PNG bytes
        _, img_encoded = cv2.imencode('.png', frame)
        img_bytes = img_encoded.tobytes()

        # Send to inference API
        try:
            response = requests.post(
                "http://34.57.54.56:8080/predict",
                files={"file": ("frame.png", img_bytes, "image/png")},
                timeout=10
            )

            if response.status_code == 200:
                prediction = response.json()
                for item in prediction.get("summary", []):
                    drum_hit = item["hit_drum"]
                    hits_total[drum_hit] += 1
                    hits_per_second[current_second][drum_hit] += 1

            else:
                print(f"[{peer.myid}] Error from API: {response.status_code}")

        except Exception as e:
            print(f"[{peer.myid}] Failed to send frame: {e}")

    cap.release()

    # Prepare result to send back
    result_data = {
        "total_hits": hits_total,
        "per_second_hits": {}
    }

    # Convert defaultdict to normal dict for JSON serialization
    for sec, hits in hits_per_second.items():
        result_data["per_second_hits"][str(sec)] = dict(hits)

    result_json = json.dumps(result_data)

    conn.senddata("MLRS", result_json)

def ml_response_handler(peer, msgdata):
    print(f"[{peer.myid}] Received ML response")

    # Parse JSON
    try:
        data = json.loads(msgdata)
    except json.JSONDecodeError:
        print("Invalid ML response received (not valid JSON):")
        print(msgdata)
        return

    total_hits = data.get("total_hits", {})
    per_second_hits = data.get("per_second_hits", {})

    print("\n=== Total Hits Over Session ===")
    for drum, count in total_hits.items():
        print(f"{drum}: {count}")

    print("\n=== Hits Per Second ===")
    for second, hits in sorted(per_second_hits.items(), key=lambda x: int(x[0])):
        print(f"Second {second}:")
        for drum, count in hits.items():
            print(f"  {drum}: {count}")