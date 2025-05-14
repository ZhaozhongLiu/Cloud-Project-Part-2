# bt_utils.py
import json, os, asyncio
from google.cloud import storage
from kademlia.network import Server as KadServer
from btpeer import BTPeer
import threading

BOOTSTRAP_NODE = ("127.0.0.1", 7000)

# ---- start / bootstrap DHT ----
def init_dht(peer: BTPeer):

    kad_port = peer.serverport + 10000
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    kad = KadServer()

    async def _start():
        await kad.listen(kad_port)
        if (peer.serverhost, peer.serverport) != BOOTSTRAP_NODE:
            await kad.bootstrap([(BOOTSTRAP_NODE[0], BOOTSTRAP_NODE[1] + 10000)])
        # store ourselves
        await kad.set(peer.myid, json.dumps({
            "host": peer.serverhost,
            "port": peer.serverport,
            "type": peer.peertype,
        }))
        # announce service
        key = f"svc:{peer.peertype.upper()}"
        raw = await kad.get(key) or "[]"
        lst = json.loads(raw)
        if peer.myid not in lst:
            lst.append(peer.myid)
            await kad.set(key, json.dumps(lst))

    loop.run_until_complete(_start())
    threading.Thread(target=loop.run_forever, daemon=True).start()

    return kad, loop

# ---- dynamic router ----
def direct_router_factory(peer, kad, loop):
    def _direct_router(pid: str):
        # first check local cache
        try:
            host, port, _ = peer.peers[pid]
            return pid, host, port
        except KeyError:
            future = asyncio.run_coroutine_threadsafe(kad.get(pid), loop)
            raw = future.result(timeout=5)
            if not raw:
                return (None, None, None)
            info = json.loads(raw)
            peer.add_peer(pid, info["host"], info["port"], info["type"])
            return pid, info["host"], info["port"]
    return _direct_router

# ---- find the first peer offering a service ----
def find_peer_for_service(kad, loop, service_type: str, timeout=5):
    key = f"svc:{service_type.upper()}"
    future = asyncio.run_coroutine_threadsafe(kad.get(key), loop)
    try:
        raw = future.result(timeout=timeout)
    except:
        return None
    if not raw:
        return None
    ids = json.loads(raw)
    if not ids:
        return None
    return ids[0]

# ---- GCS helpers ----
def upload_to_gcs(bucket_name, path):
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(os.path.basename(path))
    blob.upload_from_filename(path)
    blob.make_public()
    return blob.public_url

def delete_from_gcs(bucket, blob_name):
    client = storage.Client()
    bucket = client.bucket(bucket)
    bucket.blob(blob_name).delete()

# ---- high-level peer requests ----
def request_ml(peer, kad, loop, bucket, video_path):
    target = find_peer_for_service(kad, loop, "ML")
    if not target:
        raise RuntimeError("No ML peer")
    url = upload_to_gcs(bucket, video_path)
    replies = peer.send_to_peer(target, "MLRQ", url, waitreply=True)
    for t, d in replies:
        if t=="MLRS":
            delete_from_gcs(bucket, os.path.basename(video_path))
            return json.loads(d)
    raise RuntimeError("MLRS never arrived")

def request_iot(peer, kad, loop, start, end):
    target = find_peer_for_service(kad, loop, "IOT")
    if not target:
        raise RuntimeError("No IoT peer")
    payload = f"{start}|{end}"
    replies = peer.send_to_peer(target, "IORQ", payload, waitreply=True)
    for t, d in replies:
        if t=="IORS":
            return json.loads(d)
    raise RuntimeError("IORS never arrived")

def bc_store(peer, kad, loop, data):
    target = find_peer_for_service(kad, loop, "BC") or peer.myid
    payload = json.dumps(data)
    replies = peer.send_to_peer(target, "BCRQ", f"STORE {payload}", waitreply=True)
    for t, d in replies:
        if t=="BCRS":
            return d
    raise RuntimeError("BCRS never arrived")

def bc_fetch(peer, kad, loop):
    target = find_peer_for_service(kad, loop, "BC") or peer.myid
    replies = peer.send_to_peer(target, "BCRQ", "FETCH", waitreply=True)
    for msg_type, msg_data in replies:
        if msg_type == "BCRS":
            from handlers import bc_handlers as _bc
            _bc.bc_response_handler(peer, msg_data)
