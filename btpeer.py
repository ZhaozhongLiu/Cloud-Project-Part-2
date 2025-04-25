#!/usr/bin/env python3
"""
btpeer.py – basic P2P networking primitives (cleaned & reformatted)
"""

import socket
import struct
import threading
import time
import traceback


# --------------------------------------------------------------------------- #
# Utility
# --------------------------------------------------------------------------- #
def btdebug(msg: str) -> None:
    """Print a message tagged with the current thread name (if debug mode)."""
    print(f"[{threading.current_thread().name}] {msg}")


# --------------------------------------------------------------------------- #
# Core peer class
# --------------------------------------------------------------------------- #
class BTPeer:
    """Core functionality for a peer in a P2P network."""

    # ----------------------------------------------------------------------- #
    # Construction / initialisation
    # ----------------------------------------------------------------------- #
    def __init__(
        self,
        maxpeers: int,
        serverport: int,
        myid: str | None = None,
        serverhost: str | None = None,
    ):
        """Create a peer servant.

        Args:
            maxpeers: Maximum number of peers (0 = unlimited).
            serverport: Port this peer listens on.
            myid: Optional canonical peer ID string.
            serverhost: Override host/IP, otherwise auto-detect.
        """
        self.debug: bool = False

        self.maxpeers = int(maxpeers)
        self.serverport = int(serverport)

        self.serverhost = serverhost or self._init_server_host()
        self.myid = myid or f"{self.serverhost}:{self.serverport}"

        self.peerlock = threading.Lock()          # protects self.peers
        self.peers: dict[str, tuple[str, int]] = {}  # peerid → (host, port)
        self.shutdown: bool = False

        self.handlers: dict[str, callable] = {}   # 4-char msgtype → handler
        self.router: callable | None = None       # routing callback
        self.router = lambda pid: (pid, *self.peers.get(pid, (None, None))) #当 peers 表里有目标 pid 时就能“直连”；没有的话返回 (None, None, None)

    # ----------------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------------- #
    def _init_server_host(self) -> str:
        """Determine the local IP address by making an outbound connection."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect(("www.google.com", 80))
            return s.getsockname()[0]
        finally:
            s.close()

    def _debug(self, msg: str) -> None:
        if self.debug:
            btdebug(msg)

    # ----------------------------------------------------------------------- #
    # Networking helpers
    # ----------------------------------------------------------------------- #
    def _handle_peer(self, clientsock: socket.socket) -> None:
        """Handle a newly accepted peer connection."""
        self._debug(f"New child {threading.current_thread().name}")
        self._debug(f"Connected {clientsock.getpeername()}")

        host, port = clientsock.getpeername()
        peerconn = BTPeerConnection(None, host, port, sock=clientsock, debug=False)

        try:
            msgtype, msgdata = peerconn.recvdata()
            if msgtype:
                msgtype = msgtype.upper()
            if msgtype not in self.handlers:
                self._debug(f"Not handled: {msgtype}: {msgdata}")
            else:
                self._debug(f"Handling peer msg: {msgtype}: {msgdata}")
                self.handlers[msgtype](peerconn, msgdata)
        except KeyboardInterrupt:
            raise
        except Exception:
            if self.debug:
                traceback.print_exc()

        self._debug(f"Disconnecting {clientsock.getpeername()}")
        peerconn.close()

    def _run_stabilizer(self, stabilizer: callable, delay: float) -> None:
        while not self.shutdown:
            stabilizer()
            time.sleep(delay)

    # ----------------------------------------------------------------------- #
    # Public API – configuration
    # ----------------------------------------------------------------------- #
    def set_myid(self, myid: str) -> None:
        self.myid = myid

    def start_stabilizer(self, stabilizer: callable, delay: float) -> None:
        """Run *stabilizer* every *delay* seconds in a background thread."""
        t = threading.Thread(target=self._run_stabilizer, args=(stabilizer, delay))
        t.daemon = True
        t.start()

    def add_handler(self, msgtype: str, handler: callable) -> None:
        """Register *handler* for 4-char *msgtype*."""
        assert len(msgtype) == 4, "msgtype must be exactly 4 characters"
        self.handlers[msgtype] = handler

    def add_router(self, router: callable) -> None:
        """Register a routing callback.

        Router signature: peerid → (next_peer_id, host, port) | (None, …)
        """
        self.router = router

    # ----------------------------------------------------------------------- #
    # Peer list maintenance
    # ----------------------------------------------------------------------- #
    def add_peer(self, peerid: str, host: str, port: int) -> bool:
        """Add a peer to known list (respects *maxpeers*)."""
        if peerid in self.peers:
            return False
        if self.maxpeers and len(self.peers) >= self.maxpeers:
            return False

        self.peers[peerid] = (host, int(port))
        return True

    def get_peer(self, peerid: str) -> tuple[str, int]:
        return self.peers[peerid]

    def remove_peer(self, peerid: str) -> None:
        self.peers.pop(peerid, None)

    def get_peer_ids(self) -> list[str]:
        return list(self.peers.keys())

    def number_of_peers(self) -> int:
        return len(self.peers)

    def max_peers_reached(self) -> bool:
        return self.maxpeers > 0 and len(self.peers) >= self.maxpeers

    # ----------------------------------------------------------------------- #
    # Socket helpers
    # ----------------------------------------------------------------------- #
    @staticmethod
    def _make_server_socket(port: int, backlog: int = 5) -> socket.socket:
        """Return a bound & listening socket."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", port))
        s.listen(backlog)
        return s

    # ----------------------------------------------------------------------- #
    # Messaging
    # ----------------------------------------------------------------------- #
    def send_to_peer(
        self, peerid: str, msgtype: str, msgdata: str, waitreply: bool = True
    ):
        """Route a message to *peerid* using self.router."""
        if not self.router:
            self._debug("No router set")
            return None

        nextpid, host, port = self.router(peerid)
        if not nextpid:
            self._debug(f"Unable to route {msgtype} to {peerid}")
            return None

        return self._connect_and_send(
            host, port, msgtype, msgdata, pid=nextpid, waitreply=waitreply
        )

    def _connect_and_send(
        self,
        host: str,
        port: int,
        msgtype: str,
        msgdata: str,
        *,
        pid: str | None = None,
        waitreply: bool = True,
    ):
        replies: list[tuple[str, str]] = []
        try:
            peerconn = BTPeerConnection(pid, host, port, debug=self.debug)
            peerconn.senddata(msgtype, msgdata)
            self._debug(f"Sent {pid}: {msgtype}")

            if waitreply:
                onereply = peerconn.recvdata()
                while onereply != (None, None):
                    replies.append(onereply)
                    self._debug(f"Reply from {pid}: {onereply}")
                    onereply = peerconn.recvdata()
            peerconn.close()
        except KeyboardInterrupt:
            raise
        except Exception:
            if self.debug:
                traceback.print_exc()
        return replies

    # ----------------------------------------------------------------------- #
    # Liveness check
    # ----------------------------------------------------------------------- #
    def check_live_peers(self) -> None:
        """Ping all known peers and drop those that do not respond."""
        dead = []
        for pid, (host, port) in self.peers.items():
            try:
                self._debug(f"Ping {pid}")
                peerconn = BTPeerConnection(pid, host, port, debug=self.debug)
                peerconn.senddata("PING", "")
                peerconn.close()
            except Exception:
                dead.append(pid)

        with self.peerlock:
            for pid in dead:
                self.peers.pop(pid, None)

    # ----------------------------------------------------------------------- #
    # Main server loop
    # ----------------------------------------------------------------------- #
    def mainloop(self) -> None:
        server = self._make_server_socket(self.serverport)
        server.settimeout(2)
        self._debug(f"Server started: {self.myid} ({self.serverhost}:{self.serverport})")

        while not self.shutdown:
            try:
                self._debug("Awaiting connections …")
                clientsock, _ = server.accept()
                clientsock.settimeout(None)

                t = threading.Thread(target=self._handle_peer, args=(clientsock,))
                t.daemon = True
                t.start()
            except KeyboardInterrupt:
                print("KeyboardInterrupt → shutting down")
                self.shutdown = True
            except socket.timeout:
                continue
            except Exception:
                if self.debug:
                    traceback.print_exc()

        self._debug("Main loop exiting")
        server.close()


# --------------------------------------------------------------------------- #
# Peer connection helper class
# --------------------------------------------------------------------------- #
class BTPeerConnection:
    """Lightweight wrapper around a socket for peer messaging."""

    def __init__(
        self,
        peerid: str | None,
        host: str,
        port: int,
        *,
        sock: socket.socket | None = None,
        debug: bool = False,
    ):
        self.id = peerid
        self.debug = debug

        if sock:
            self.s = sock
        else:
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.s.connect((host, int(port)))

        # binary read/write, unbuffered
        self.sd = self.s.makefile("rwb", buffering=0)

    # ----------------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------------- #
    @staticmethod
    def _make_msg(msgtype: str, msgdata: str) -> bytes:
        msg_bytes = msgdata.encode()
        msglen = len(msg_bytes)
        return struct.pack(f"!4sL{msglen}s", msgtype.encode(), msglen, msg_bytes)

    def _debug(self, msg: str) -> None:
        if self.debug:
            btdebug(msg)

    # ----------------------------------------------------------------------- #
    # Public API
    # ----------------------------------------------------------------------- #
    def senddata(self, msgtype: str, msgdata: str) -> bool:
        """Send a framed message. Return True on success."""
        try:
            self.sd.write(self._make_msg(msgtype, msgdata))
            self.sd.flush()
            return True
        except KeyboardInterrupt:
            raise
        except Exception:
            if self.debug:
                traceback.print_exc()
            return False

    def recvdata(self) -> tuple[str | None, str | None]:
        """Receive one framed message."""
        try:
            msgtype_raw = self.sd.read(4)
            if not msgtype_raw:
                return (None, None)

            len_raw = self.sd.read(4)
            msglen = struct.unpack("!L", len_raw)[0]

            data = self.sd.read(msglen)
            if len(data) != msglen:
                return (None, None)

            return (msgtype_raw.decode(), data.decode())
        except KeyboardInterrupt:
            raise
        except Exception:
            if self.debug:
                traceback.print_exc()
            return (None, None)

    def close(self) -> None:
        self.s.close()
        self.sd.close()

    def __str__(self) -> str:  # pragma: no cover
        return f"|{self.id}|"