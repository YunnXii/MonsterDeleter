from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QIODevice, QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket


SERVER_NAME = "YunnXii-JiaqiCleaner-Resident-v1"
PROTOCOL_VERSION = 1


class ResidentAlreadyRunning(RuntimeError):
    """Raised when another process wins the resident-server startup race."""


def make_command(target: Path | None = None) -> dict[str, object]:
    if target is None:
        return {"version": PROTOCOL_VERSION, "type": "activate"}
    return {
        "version": PROTOCOL_VERSION,
        "type": "target",
        "path": str(target),
    }


def encode_command(command: dict[str, object]) -> bytes:
    return (json.dumps(command, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def decode_command(payload: bytes) -> dict[str, object] | None:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("version") != PROTOCOL_VERSION:
        return None
    if value.get("type") not in {"activate", "target"}:
        return None
    if value.get("type") == "target" and not isinstance(value.get("path"), str):
        return None
    return value


def _resident_endpoint_is_live(*, timeout_ms: int = 350) -> bool:
    probe = QLocalSocket()
    probe.connectToServer(SERVER_NAME, QIODevice.OpenModeFlag.WriteOnly)
    if not probe.waitForConnected(timeout_ms):
        return False
    probe.disconnectFromServer()
    return True


def send_command(command: dict[str, object], *, timeout_ms: int = 650) -> bool:
    """Send one command to an already-running resident instance."""
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME, QIODevice.OpenModeFlag.WriteOnly)
    if not socket.waitForConnected(timeout_ms):
        return False

    if socket.write(encode_command(command)) < 0:
        socket.abort()
        return False
    socket.flush()

    # Local sockets can drain a tiny JSON command synchronously. In that case
    # waitForBytesWritten() may have nothing left to wait for, which is success,
    # not a failed IPC send.
    ok = socket.bytesToWrite() == 0 or socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    return bool(ok)


class LocalCommandServer(QObject):
    command_received = pyqtSignal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._accept_pending)
        self._buffers: dict[int, bytes] = {}

    def start(self) -> None:
        if self.server.isListening():
            return
        if self.server.listen(SERVER_NAME):
            return

        # listen() can fail for two very different reasons: an actually-running
        # resident won a near-simultaneous startup race, or a crashed process
        # left a stale endpoint behind. Probe before removing anything.
        if _resident_endpoint_is_live():
            raise ResidentAlreadyRunning("已有家琦常驻实例")

        QLocalServer.removeServer(SERVER_NAME)
        if self.server.listen(SERVER_NAME):
            return

        # Another process may have claimed the name between cleanup and listen.
        if _resident_endpoint_is_live():
            raise ResidentAlreadyRunning("已有家琦常驻实例")
        raise RuntimeError(f"无法启动常驻通信：{self.server.errorString()}")

    def close(self) -> None:
        self.server.close()
        QLocalServer.removeServer(SERVER_NAME)

    def _accept_pending(self) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if socket is None:
                continue
            key = id(socket)
            self._buffers[key] = b""
            socket.readyRead.connect(lambda s=socket: self._consume(s))
            socket.disconnected.connect(lambda k=key: self._buffers.pop(k, None))
            socket.disconnected.connect(socket.deleteLater)
            self._consume(socket)

    def _consume(self, socket: QLocalSocket) -> None:
        key = id(socket)
        data = self._buffers.get(key, b"") + bytes(socket.readAll())

        while b"\n" in data:
            line, data = data.split(b"\n", 1)
            command = decode_command(line)
            if command is not None:
                self.command_received.emit(command)

        self._buffers[key] = data
