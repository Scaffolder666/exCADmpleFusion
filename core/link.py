"""Link between two Fusion instances (version A, as in History in Motion).

HiM renders the example in a second Fusion instance and talks to the
user's instance over a local socket. The first instance to start binds the
port and becomes the *workspace* (the user's own design); the next one
connects and becomes the *reference* instance (the designer's model and the
tutorial). Messages are JSON lines on 127.0.0.1 only.

Pure Python. ``on_message`` is called on a background thread: the add-in
forwards it to Fusion's main thread with a custom event.
"""
import json
import socket
import threading

DEFAULT_PORT = 52731
WORKSPACE, REFERENCE = "workspace", "reference"
MAX_LINE = 4 * 1024 * 1024


class InstanceLink:
    def __init__(self, on_message, port=DEFAULT_PORT, host="127.0.0.1"):
        self.on_message = on_message
        self.port, self.host = port, host
        self.role = None
        self._server = None
        self._peer = None
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self.on_connect = None

    # --- lifecycle ---------------------------------------------------------------
    def start(self):
        """Bind (workspace) or connect (reference). Returns the role."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            server.bind((self.host, self.port))
        except OSError:
            server.close()
            peer = socket.create_connection((self.host, self.port), timeout=3)
            peer.settimeout(None)
            self.role = REFERENCE
            self._attach(peer)
            return self.role
        server.listen(1)
        self._server = server
        self.role = WORKSPACE
        threading.Thread(target=self._accept, daemon=True).start()
        return self.role

    def stop(self):
        self._stopped.set()
        for sock in (self._peer, self._server):
            if not sock:
                continue
            try:
                sock.shutdown(socket.SHUT_RDWR)   # wakes the reader and tells the peer
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        self._peer = self._server = None

    @property
    def connected(self):
        return self._peer is not None

    # --- io ---------------------------------------------------------------------------
    def send(self, message):
        data = (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")
        with self._lock:
            if self._peer is None:
                return False
            try:
                self._peer.sendall(data)
                return True
            except OSError:
                self._peer = None
                return False

    def _accept(self):
        while not self._stopped.is_set():
            try:
                peer, _addr = self._server.accept()
            except OSError:
                return
            with self._lock:
                old, self._peer = self._peer, None
            if old:
                old.close()
            self._attach(peer)

    def _attach(self, peer):
        with self._lock:
            self._peer = peer
        if self.on_connect:
            self.on_connect()
        threading.Thread(target=self._read, args=(peer,), daemon=True).start()

    def _read(self, peer):
        buffer = b""
        while not self._stopped.is_set():
            try:
                chunk = peer.recv(65536)
            except OSError:
                break
            if not chunk:
                break
            buffer += chunk
            if len(buffer) > MAX_LINE:
                break
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                try:
                    message = json.loads(line.decode("utf-8"))
                except ValueError:
                    continue
                if isinstance(message, dict):
                    self.on_message(message)
        with self._lock:
            if self._peer is peer:
                self._peer = None
        if self.on_message:
            self.on_message({"cmd": "_disconnected"})
