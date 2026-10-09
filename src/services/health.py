import os
import socket


def notify_ready():
    """Tell systemd that Telegram initialization succeeded; local runs need no socket."""
    address = os.getenv('NOTIFY_SOCKET')
    if not address:
        return
    if address.startswith('@'):
        address = '\0' + address[1:]
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as connection:
        connection.connect(address)
        connection.sendall(b'READY=1')
