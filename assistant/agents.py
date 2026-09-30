import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class AgentProfile:
    id: str
    name: str
    tier: int
    provider: str
    model: str
    prompts: list[str]
    tools: list[str]
    context: dict
    memory: dict = field(default_factory=dict)
    model_settings: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.tier not in (1, 2, 3):
            raise ValueError('V0 supports tiers 1, 2 and 3')
        for key in ('max_characters', 'tool_result_characters', 'transcript_characters'):
            if type(self.context.get(key)) is not int or self.context[key] <= 0:
                raise ValueError(f'Agent {self.id}: context.{key} must be a positive integer')
        if not all(isinstance(value, str) for value in self.prompts + self.tools):
            raise ValueError('Agent prompts and tools must be lists of strings')


class AgentManager:
    def __init__(self, store):
        self.store = store

    def seed(self, directory):
        # Seed once. Subsequent profile updates use this manager; SQLite wins.
        for path in sorted(Path(directory).glob('*.json')):
            profile = AgentProfile(**json.loads(path.read_text(encoding='utf-8-sig')))
            self.store.execute('INSERT OR IGNORE INTO agents (id,name,config_json) VALUES (?,?,?)',
                               (profile.id, profile.name, json.dumps(asdict(profile))))

    def get(self, agent_id):
        row = self.store.one('SELECT config_json FROM agents WHERE id=?', (agent_id,))
        if row is None:
            raise ValueError(f'Unknown agent: {agent_id}')
        return AgentProfile(**json.loads(row['config_json']))

    def update(self, profile):
        AgentProfile(**asdict(profile))
        self.store.execute('''INSERT INTO agents (id,name,config_json) VALUES (?,?,?)
            ON CONFLICT(id) DO UPDATE SET name=excluded.name,config_json=excluded.config_json''',
                           (profile.id, profile.name, json.dumps(asdict(profile))))
