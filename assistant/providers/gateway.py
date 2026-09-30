import json
import random
import time
from dataclasses import asdict

from assistant.models import ProviderError


class ProviderGateway:
    def __init__(self, store, adapters, retry, sleep=time.sleep, random_value=random.random):
        self.store = store
        self.adapters = adapters
        self.retry = retry
        self.sleep = sleep
        self.random_value = random_value

    def complete(self, request, run_id, session_id):
        adapter = self.adapters.get(request.provider)
        if adapter is None:
            raise ProviderError('configuration', f'Unknown provider: {request.provider}')
        payload = adapter.prepare(request)
        waited = 0.0
        for attempt in range(self.retry['max_attempts']):
            call_id = self.store.execute('''INSERT INTO api_calls
                (run_id,session_id,agent_id,provider,model,request_json,status)
                VALUES (?,?,?,?,?,?,'running')''',
                (run_id, session_id, request.agent_id, request.provider, request.model,
                 json.dumps({'generic': asdict(request), 'wire': payload}, ensure_ascii=False)))
            try:
                response = adapter.complete(request, payload)
            except ProviderError as error:
                self.store.execute('''UPDATE api_calls SET status='failed',error_type=?,
                    response_json=?,finished_at=CURRENT_TIMESTAMP WHERE id=?''',
                    (error.kind, json.dumps({'error': str(error), 'raw': error.raw}), call_id))
                if not error.retryable or attempt + 1 >= self.retry['max_attempts']:
                    raise
                delay = min(self.retry['base_backoff_seconds'] * 2 ** attempt,
                            self.retry['max_backoff_seconds'])
                if self.retry['jitter']:
                    delay *= 0.5 + 0.5 * self.random_value()
                if waited + delay > self.retry['max_wait_seconds']:
                    raise
                self.sleep(delay)
                waited += delay
            except Exception as error:
                self.store.execute('''UPDATE api_calls SET status='failed',error_type='adapter_error',
                    response_json=?,finished_at=CURRENT_TIMESTAMP WHERE id=?''',
                    (json.dumps({'error': type(error).__name__}), call_id))
                raise
            else:
                response.api_call_id = call_id
                self.store.execute('''UPDATE api_calls SET status='completed',response_json=?,
                    input_tokens=?,output_tokens=?,finished_at=CURRENT_TIMESTAMP WHERE id=?''',
                    (json.dumps(asdict(response), ensure_ascii=False), response.input_tokens,
                     response.output_tokens, call_id))
                return response
        raise RuntimeError('Invalid retry configuration')
