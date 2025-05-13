import json
from datetime import datetime
import paho.mqtt.client as mqtt, ssl

iot_data_log = []

def iot_response_handler(peer, msgdata):
    try:
        data = json.loads(msgdata)
        print(data)
        if isinstance(data, list):
            print(f"[{peer.myid}] IoT Data Received ({len(data)} entries):")
            for entry in data:
                print(f" - {entry['timestamp']} | Vibration: {entry['vibration_level']} | Noise (db): {entry['room_noise (db)']}")
        elif isinstance(data, dict) and "error" in data:
            print(f"[{peer.myid}] IoT Error: {data['error']}")
        else:
            print(f"[{peer.myid}] Unknown IoT response format: {data}")
    except Exception as e:
        print(f"[{peer.myid}] Failed to parse IoT response: {msgdata} ({e})")

from datetime import datetime, timezone

def iot_request_handler(peer, conn, msgdata):
    print(f"[{peer.myid}] Received IoT request with time filter: {msgdata}")
    try:
        start_time_str, end_time_str = msgdata.split("|")

        # Assume user input is UTC and make both aware
        start_time = datetime.fromisoformat(start_time_str).replace(tzinfo=timezone.utc)
        end_time = datetime.fromisoformat(end_time_str).replace(tzinfo=timezone.utc)

        filtered_data = []
        for entry in iot_data_log:
            try:
                # Make sure entry timestamp is also aware
                entry_time = datetime.fromisoformat(entry['timestamp'].replace("Z", "+00:00"))

                if start_time <= entry_time <= end_time:
                    filtered_data.append(entry)
            except Exception as parse_err:
                print(f"[{peer.myid}] Skipping malformed timestamp: {entry['timestamp']} ({parse_err})")
                continue

        print(f"[{peer.myid}] Filtered {len(filtered_data)} entries")
        conn.senddata("IORS", json.dumps(filtered_data))

    except Exception as e:
        conn.senddata("IORS", json.dumps({"error": f"Invalid request format: {str(e)}"}))


def on_connect(client, userdata, flags, rc):
    result, mid = client.subscribe("drumkit/vibration", qos=1)

def on_message(client, userdata, msg):
    global iot_data_log
    data = json.loads(msg.payload.decode())
    iot_data_log.append(data)
    # print(f"[{peer.myid}] Logged IoT data: {data}")

def start_aws_iot_listener():
    client = mqtt.Client(client_id="drum-vibration-subscriber")
    client.tls_set(ca_certs="root-CA.crt",
                   certfile="vibration_sensor.cert.pem",
                   keyfile="vibration_sensor.private.key",
                   tls_version=ssl.PROTOCOL_TLSv1_2)
    client.on_connect = on_connect

    client.on_message = on_message
    client.connect("a23b8qpya3dwq-ats.iot.us-east-1.amazonaws.com", 8883, 60)
    client.loop_start()