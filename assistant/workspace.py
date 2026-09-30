from datetime import datetime, timezone
from pathlib import Path


class Workspace:
    def __init__(self, root, store, max_read_bytes=100000):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = store
        self.max_read_bytes = max_read_bytes

    def path(self, relative):
        candidate = (self.root / relative).resolve()
        if not candidate.is_relative_to(self.root) or candidate == self.root:
            raise ValueError('File must be inside the workspace')
        return candidate

    def index(self, path, description=''):
        self.store.execute('''INSERT INTO files (path,name,type,size,description) VALUES (?,?,?,?,?)
            ON CONFLICT(path) DO UPDATE SET size=excluded.size,description=excluded.description''',
            (str(path.relative_to(self.root)), path.name, path.suffix, path.stat().st_size, description))

    def read(self, path):
        target = self.path(path)
        with target.open('rb') as stream:
            data = stream.read(self.max_read_bytes + 1)
        truncated = len(data) > self.max_read_bytes
        text = data[:self.max_read_bytes].decode('utf-8', errors='replace')
        self.index(target)
        return {'text': text, 'truncated': truncated}

    def write_note(self, path, content):
        target = self.path(path)
        if target.suffix.lower() != '.md':
            raise ValueError('Notes must use .md filenames')
        target.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create: approval cannot silently overwrite existing documents.
        with target.open('x', encoding='utf-8') as stream:
            stream.write(content)
        self.index(target, 'Approved note')
        return {'path': str(target.relative_to(self.root)), 'created': True}

    def log_memory(self, content):
        day = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        target = self.path(f'activity/{day}.md')
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('a', encoding='utf-8') as stream:
            stream.write(f"\n## {datetime.now(timezone.utc).isoformat()}\n\n{content}\n")
        self.index(target, 'Detailed memory activity log (UTC)')
