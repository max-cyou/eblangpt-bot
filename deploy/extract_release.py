"""Extract a repository archive without links or paths outside the release."""
import sys
import tarfile
from pathlib import Path, PurePosixPath


def extract(archive_path, destination):
    destination = Path(destination).resolve()
    with tarfile.open(archive_path, 'r:gz') as archive:
        members = archive.getmembers()
        if sum(member.size for member in members) > 100 * 1024 * 1024:
            raise ValueError('Release archive exceeds 100 MiB')
        for member in members:
            name = PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts or not (member.isfile() or member.isdir()):
                raise ValueError('Unsupported archive entry')
            if not (destination / member.name).resolve().is_relative_to(destination):
                raise ValueError('Archive path escapes release directory')
            if name.parts and name.parts[0] in ('.env', '.git', 'data', '.venv'):
                raise ValueError('Release contains local state or credentials')
        archive.extractall(destination, members=members)


if __name__ == '__main__':
    extract(sys.argv[1], sys.argv[2])
