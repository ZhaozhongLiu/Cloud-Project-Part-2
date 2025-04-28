def ml_request_handler(peer, conn, msgdata):
    print(f"[{peer.myid}] Received ML request with data: {msgdata}")
    result = f"Processed({msgdata})"
    conn.senddata("MLRS", result)  # MLRS = ML Response

def ml_response_handler(peer, msgdata):
    print(f"[{peer.myid}] Received ML response: {msgdata}")