import json
import logging
from dataclasses import asdict

from assistant.models import LLMRequest, Message

logger = logging.getLogger(__name__)


class ContextOverflow(ValueError):
    pass


class ContextService:
    def __init__(self, store, root, registry):
        self.store = store
        self.root = root
        self.registry = registry

    def transcript(self, session_id):
        rows = self.store.rows('SELECT * FROM messages WHERE session_id=? ORDER BY id', (session_id,))
        state = self.store.one('SELECT * FROM context_state WHERE session_id=?', (session_id,))
        if state and state['retained_ids_json'] is not None:
            retained = set(json.loads(state['retained_ids_json']))
            rows = [row for row in rows if row['id'] in retained or row['id'] > state['through_message_id']]
        return rows

    def tool_result(self, profile, name, result, call_id=''):
        text = json.dumps(result, ensure_ascii=False)
        limit = profile.context['tool_result_characters']
        if len(text) > limit:
            marker = '\n[truncated; full result in tool_calls]'
            text = text[:max(0, limit - len(marker))] + marker[:limit]
        return Message('tool', text, tool_name=name, tool_call_id=call_id)

    def build(self, profile, session_id, current_message_id, continuation=None):
        current = self.store.one('SELECT * FROM messages WHERE id=? AND session_id=?',
                                 (current_message_id, session_id))
        if current is None:
            raise ValueError('Current input is not in the session')
        prefix = '\n\n'.join((self.root / path).read_text(encoding='utf-8') for path in profile.prompts)
        dynamic = []
        for layer in profile.context.get('memory_layers', []):
            items = self.store.rows('SELECT content FROM memory_items WHERE layer=? ORDER BY id', (layer,))
            if items:
                dynamic.append(f'[{layer} memory]\n' + '\n'.join(item['content'] for item in items))
        if profile.tier == 3:
            state = self.store.one('SELECT working_summary FROM context_state WHERE session_id=?', (session_id,))
            if state and state['working_summary']:
                dynamic.append('[Expert working summary]\n' + state['working_summary'])
        memory = '\n\n'.join(dynamic)
        history = []
        if profile.tier != 1:
            session = self.store.one('SELECT * FROM sessions WHERE id=?', (session_id,))
            used = 0
            rows = [row for row in self.transcript(session_id) if row['id'] < current_message_id]
            for row in reversed(rows):
                used += len(row['content'])
                if used > profile.context['transcript_characters']:
                    break
                is_caller = (row['sender_type'], row['sender_id']) == (
                    session['participant_a_type'], session['participant_a_id'])
                history.insert(0, Message('user' if is_caller else 'assistant', row['content']))
        fixed = [Message('user', current['content']), *(continuation or [])]
        tools = self.registry.schemas(profile.tools)

        def request():
            return LLMRequest(profile.id, profile.provider, profile.model,
                              prefix + ('\n\n[Context data]\n' + memory if memory else ''),
                              history + fixed, tools, profile.model_settings)

        limit = profile.context['max_characters']
        size = lambda req: len(json.dumps(asdict(req), ensure_ascii=False))
        built = request()
        while size(built) > limit and history:
            history.pop(0)
            built = request()
        while size(built) > limit and memory:
            # This limits insertion only; persistent memory is left untouched.
            memory = memory[:max(0, len(memory) - (size(built) - limit) - 64)]
            built = request()
        if size(built) > limit:
            raise ContextOverflow('System prompt, tools, current input or tool continuation exceeds context cap')
        logger.info('Context agent=%s session=%s characters=%s messages=%s',
                    profile.id, session_id, size(built), len(built.messages))
        return built
