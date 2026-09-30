from dataclasses import dataclass


@dataclass
class ApprovalRequest:
    id: int
    run_id: str
    agent_id: str
    tool_name: str
    arguments: dict


class ApprovalService:
    def __init__(self, store):
        self.store = store

    def pending(self):
        return self.store.rows('''SELECT a.id,a.tool_call_id,t.run_id,t.tool_name,t.arguments_json
            FROM approvals a JOIN tool_calls t ON t.id=a.tool_call_id
            WHERE a.status='pending' ORDER BY a.id''')

    def resolve(self, approval_id, approved):
        with self.store.connect() as connection:
            row = connection.execute('SELECT * FROM approvals WHERE id=?', (approval_id,)).fetchone()
            if row is None or row['status'] != 'pending':
                raise ValueError('Approval is absent or already resolved')
            connection.execute('UPDATE approvals SET status=?,resolved_at=CURRENT_TIMESTAMP WHERE id=?',
                               ('approved' if approved else 'denied', approval_id))
            tool = connection.execute('SELECT run_id FROM tool_calls WHERE id=?', (row['tool_call_id'],)).fetchone()
            return tool['run_id']
