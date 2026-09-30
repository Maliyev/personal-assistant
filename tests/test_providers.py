import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from assistant.agents import AgentManager
from assistant.config import ROOT, load_config
from assistant.models import LLMRequest, LLMResponse, Message, ProviderError
from assistant.providers.gateway import ProviderGateway
from assistant.providers.gemini import GeminiAdapter
from assistant.storage import Store


class ScriptedAdapter:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def prepare(self, request):
        return {'input': request.messages[-1].text}

    def complete(self, request, payload):
        self.calls += 1
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.directory.cleanup)
        self.store = Store(Path(self.directory.name) / 'test.db')
        AgentManager(self.store).seed(ROOT / 'config/agents')
        self.session = self.store.session()
        self.run = self.store.run(self.session, 'personal')
        self.request = LLMRequest('personal', 'fake', 'test', 'system', [Message('user', 'hello')])

    def test_transient_attempts_persist_and_permanent_stops(self):
        adapter = ScriptedAdapter([ProviderError('rate_limit', '429', True), LLMResponse(text='ok')])
        delays = []
        gateway = ProviderGateway(self.store, {'fake': adapter}, load_config()['retry'], sleep=delays.append)
        self.assertEqual(gateway.complete(self.request, self.run, self.session).text, 'ok')
        self.assertEqual(adapter.calls, 2)
        self.assertEqual(len(delays), 1)
        self.assertEqual([r['status'] for r in self.store.rows('SELECT status FROM api_calls ORDER BY id')], ['failed', 'completed'])
        adapter = ScriptedAdapter([ProviderError('authentication', 'bad key')])
        gateway.adapters['fake'] = adapter
        with self.assertRaises(ProviderError):
            gateway.complete(self.request, self.run, self.session)
        self.assertEqual(adapter.calls, 1)

    def test_retry_wait_budget(self):
        adapter = ScriptedAdapter([ProviderError('network', 'timeout', True)] * 20)
        retry = dict(load_config()['retry'], max_attempts=20, max_wait_seconds=2, jitter=False)
        delays = []
        with self.assertRaises(ProviderError):
            ProviderGateway(self.store, {'fake': adapter}, retry, sleep=delays.append).complete(
                self.request, self.run, self.session)
        self.assertEqual(adapter.calls, 2)
        self.assertEqual(delays, [1])

    def test_signed_tool_response_roundtrip_and_thought_not_visible(self):
        adapter = GeminiAdapter(load_config()['providers']['gemini'], 5)
        data = {'candidates': [{'content': {'role': 'model', 'parts': [
            {'text': 'hidden', 'thought': True},
            {'functionCall': {'name': 'current_time', 'args': {}, 'id': 'call-1'}, 'thoughtSignature': 'opaque'}]},
            'finishReason': 'STOP'}], 'usageMetadata': {'promptTokenCount': 12}}
        result = adapter.parse(data)
        self.assertEqual(result.text, '')
        self.assertEqual(result.input_tokens, 12)
        self.request.messages.append(result.continuation)
        self.request.messages.append(Message('tool', 'noon', tool_name='current_time', tool_call_id='call-1'))
        payload = adapter.prepare(self.request)
        self.assertEqual(payload['contents'][1]['parts'][1]['thoughtSignature'], 'opaque')
        self.assertEqual(payload['contents'][2]['parts'][0]['functionResponse']['id'], 'call-1')

    def test_blocked_and_malformed_responses(self):
        adapter = GeminiAdapter(load_config()['providers']['gemini'], 5)
        for data in ({}, {'candidates': []}, {'promptFeedback': {'blockReason': 'SAFETY'}}):
            with self.assertRaises(ProviderError):
                adapter.parse(data)

    def test_http_error_normalization_and_no_key_in_payload(self):
        for status, kind, retryable in ((400, 'invalid_request', False), (403, 'permission', False),
                                         (429, 'rate_limit', True), (503, 'provider_error', True)):
            def opener(request, timeout):
                raise HTTPError(request.full_url, status, 'test', {}, io.BytesIO(b'{"error":{"message":"test"}}'))
            adapter = GeminiAdapter(load_config()['providers']['gemini'], 5, opener)
            with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-secret'}):
                payload = adapter.prepare(self.request)
                self.assertNotIn('test-secret', str(payload))
                with self.assertRaises(ProviderError) as caught:
                    adapter.complete(self.request, payload)
            self.assertEqual(caught.exception.kind, kind)
            self.assertEqual(caught.exception.retryable, retryable)
