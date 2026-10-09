import importlib.util
import io
import os
from pathlib import Path
import socket
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from services.health import notify_ready

spec = importlib.util.spec_from_file_location('extract_release', Path(__file__).resolve().parent.parent / 'deploy/extract_release.py')
extract_release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract_release)


class DeploymentTests(unittest.TestCase):
    def test_ready_notification_and_local_run(self):
        with patch.dict(os.environ, {}, clear=True):
            notify_ready()
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'notify')
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as receiver:
                receiver.bind(path)
                receiver.settimeout(1)
                with patch.dict(os.environ, {'NOTIFY_SOCKET': path}):
                    notify_ready()
                self.assertEqual(receiver.recv(100), b'READY=1')

    def test_archive_rejects_local_state_links_and_escaping_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            for name, kind in (('../outside', tarfile.REGTYPE), ('.env', tarfile.REGTYPE), ('data/history.sqlite3', tarfile.REGTYPE), ('link', tarfile.SYMTYPE)):
                archive = Path(directory) / 'release.tar.gz'
                with tarfile.open(archive, 'w:gz') as output:
                    member = tarfile.TarInfo(name)
                    member.type = kind
                    if kind == tarfile.SYMTYPE:
                        member.linkname = '/etc/passwd'
                    else:
                        member.size = 1
                    output.addfile(member, io.BytesIO(b'x') if kind != tarfile.SYMTYPE else None)
                with self.assertRaises(ValueError):
                    extract_release.extract(archive, Path(directory) / 'release')
