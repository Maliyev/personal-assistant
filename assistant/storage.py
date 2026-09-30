"""SQLite is the structured source of truth. Files remain on disk."""
import json
import sqlite3
import uuid
from pathlib import Path


SCHEMA_VERSION = 1
SCHEMA = (
    """CREATE TABLE agents (id TEXT PRIMARY KEY, name TEXT NOT NULL,
        config_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE sessions (id TEXT PRIMARY KEY, participant_a_type TEXT NOT NULL,
        participant_a_id TEXT NOT NULL, participant_b_type TEXT NOT NULL,
        participant_b_id TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
        sender_type TEXT NOT NULL, sender_id TEXT NOT NULL, content TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE runs (id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
        agent_id TEXT NOT NULL REFERENCES agents(id), parent_run_id TEXT REFERENCES runs(id),
        status TEXT NOT NULL, started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        finished_at TEXT, error TEXT, state_json TEXT)""",
    """CREATE TABLE api_calls (id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
        session_id TEXT NOT NULL REFERENCES sessions(id), agent_id TEXT NOT NULL REFERENCES agents(id),
        provider TEXT NOT NULL, model TEXT NOT NULL, request_json TEXT NOT NULL,
        response_json TEXT, status TEXT NOT NULL, error_type TEXT, input_tokens INTEGER,
        output_tokens INTEGER, cost REAL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        finished_at TEXT)""",
    """CREATE TABLE tool_calls (id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
        session_id TEXT NOT NULL REFERENCES sessions(id), agent_id TEXT NOT NULL REFERENCES agents(id),
        api_call_id INTEGER REFERENCES api_calls(id), tool_name TEXT NOT NULL,
        arguments_json TEXT NOT NULL, result TEXT, status TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, finished_at TEXT)""",
    """CREATE TABLE approvals (id INTEGER PRIMARY KEY,
        tool_call_id INTEGER NOT NULL UNIQUE REFERENCES tool_calls(id),
        status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        resolved_at TEXT)""",
    """CREATE TABLE scheduled_jobs (id INTEGER PRIMARY KEY,
        target_agent_id TEXT NOT NULL REFERENCES agents(id), session_id TEXT NOT NULL REFERENCES sessions(id),
        payload TEXT NOT NULL, schedule TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
        next_run_at TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE memory_items (id INTEGER PRIMARY KEY, layer TEXT NOT NULL,
        content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL, type TEXT NOT NULL, size INTEGER NOT NULL, description TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    # Additional state selects active raw messages without modifying their contents.
    """CREATE TABLE context_state (session_id TEXT PRIMARY KEY REFERENCES sessions(id),
        retained_ids_json TEXT, through_message_id INTEGER NOT NULL DEFAULT 0,
        working_summary TEXT NOT NULL DEFAULT '', maintained_at TEXT)""",
    "CREATE INDEX messages_by_session ON messages(session_id, id)",
    "CREATE INDEX runs_by_session ON runs(session_id, started_at)",
    "CREATE INDEX scheduled_due ON scheduled_jobs(status, next_run_at)",
)


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('BEGIN IMMEDIATE')
            version = connection.execute('PRAGMA user_version').fetchone()[0]
            tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if version == 0 and tables:
                raise ValueError('Existing database has an unknown schema; use a new V0 database path.')
            if version > SCHEMA_VERSION:
                raise ValueError('Database schema is newer than this application.')
            if version == 0:
                for statement in SCHEMA:
                    connection.execute(statement)
                connection.execute(f'PRAGMA user_version={SCHEMA_VERSION}')

    def connect(self):
        # SQLite's context manager commits/rolls back; this subclass also closes.
        class Connection(sqlite3.Connection):
            def __exit__(self, *args):
                try:
                    return super().__exit__(*args)
                finally:
                    self.close()
        connection = sqlite3.connect(self.path, timeout=5, factory=Connection)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        return connection

    def execute(self, sql, parameters=()):
        with self.connect() as connection:
            return connection.execute(sql, parameters).lastrowid

    def rows(self, sql, parameters=()):
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(sql, parameters).fetchall()]

    def one(self, sql, parameters=()):
        rows = self.rows(sql, parameters)
        return rows[0] if rows else None

    def session(self, caller_type='user', caller_id='magerram', target='personal', session_id=None):
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            participants = (caller_type, caller_id, 'agent', target)
            if session_id is not None:
                row = connection.execute('SELECT * FROM sessions WHERE id=?', (session_id,)).fetchone()
                if row is None or tuple(row[key] for key in (
                        'participant_a_type', 'participant_a_id', 'participant_b_type', 'participant_b_id')) != participants:
                    raise ValueError('Session does not belong to these participants')
                return session_id
            if caller_type == 'user' and target == 'personal':
                row = connection.execute('''SELECT id FROM sessions WHERE participant_a_type=?
                    AND participant_a_id=? AND participant_b_type=? AND participant_b_id=?
                    ORDER BY created_at, id LIMIT 1''', participants).fetchone()
                if row:
                    return row['id']
            new_id = uuid.uuid4().hex
            connection.execute('''INSERT INTO sessions (id,participant_a_type,participant_a_id,
                participant_b_type,participant_b_id) VALUES (?,?,?,?,?)''', (new_id, *participants))
            return new_id

    def message(self, session_id, sender_type, sender_id, content):
        return self.execute('INSERT INTO messages (session_id,sender_type,sender_id,content) VALUES (?,?,?,?)',
                            (session_id, sender_type, sender_id, content))

    def run(self, session_id, agent_id, parent_run_id=None):
        run_id = uuid.uuid4().hex
        self.execute("INSERT INTO runs (id,session_id,agent_id,parent_run_id,status) VALUES (?,?,?,?,'running')",
                     (run_id, session_id, agent_id, parent_run_id))
        return run_id

    def finish(self, run_id, status='completed', error=None, state=None):
        self.execute('''UPDATE runs SET status=?,error=?,state_json=?,
            finished_at=CASE WHEN ?='waiting' THEN NULL ELSE CURRENT_TIMESTAMP END WHERE id=?''',
                     (status, error, json.dumps(state) if state is not None else None, status, run_id))
