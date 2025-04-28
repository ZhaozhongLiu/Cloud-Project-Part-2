def bc_request_handler(peer, conn, msgdata):
    print(f"[{peer.myid}] Received BC request with data: {msgdata}")
    result = f"Processed({msgdata})"
    conn.senddata("BCRS", result)  # BCRS = Blockchain Response

def bc_response_handler(peer, msgdata):
    print(f"[{peer.myid}] Received BC response: {msgdata}")