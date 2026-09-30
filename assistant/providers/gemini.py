"""Gemini REST adapter. Retry and persistence belong to ProviderGateway.

API reference: https://ai.google.dev/api/generate-content
Error policy: https://ai.google.dev/gemini-api/docs/troubleshooting
"""
import json
import os
import socket
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from assistant.models import LLMResponse, Message, ProviderError, ToolCall


class GeminiAdapter:
    def __init__(self, config, timeout, opener=urlopen):
        self.config = config
        self.timeout = timeout
        self.opener = opener
        if urlparse(config['base_url']).scheme != 'https':
            raise ValueError('Gemini base URL must use HTTPS')

    def prepare(self, request):
        contents = []
        for message in request.messages:
            if message.role == 'assistant' and 'gemini' in message.provider_data:
                content = message.provider_data['gemini']
                contents.append(content)
                continue
            if message.role == 'tool':
                function_response = {'name': message.tool_name, 'response': {'result': message.text}}
                if message.tool_call_id:
                    function_response['id'] = message.tool_call_id
                parts = [{'functionResponse': function_response}]
            else:
                parts = [{'text': message.text}] if message.text else []
                for call in message.tool_calls:
                    function_call = {'name': call.name, 'args': call.arguments}
                    if call.id:
                        function_call['id'] = call.id
                    parts.append({'functionCall': function_call})
            role = 'model' if message.role == 'assistant' else 'user'
            if contents and contents[-1]['role'] == role:
                contents[-1]['parts'].extend(parts)
            else:
                contents.append({'role': role, 'parts': parts})
        payload = {'contents': contents, 'systemInstruction': {'parts': [{'text': request.system}]}}
        if request.tools:
            payload['tools'] = [{'functionDeclarations': [
                {'name': tool.name, 'description': tool.description, 'parametersJsonSchema': tool.input_schema}
                for tool in request.tools]}]
        supported = {'temperature': 'temperature', 'max_output_tokens': 'maxOutputTokens',
                     'response_json': 'responseMimeType'}
        generation = {}
        for key, value in request.settings.items():
            if key not in supported:
                raise ProviderError('configuration', f'Unsupported model setting: {key}')
            if key == 'response_json':
                if value:
                    generation[supported[key]] = 'application/json'
            else:
                generation[supported[key]] = value
        if generation:
            payload['generationConfig'] = generation
        return payload

    def complete(self, request, payload):
        key = os.environ.get(self.config['api_key_env'])
        if not key:
            raise ProviderError('authentication', f"Missing environment variable: {self.config['api_key_env']}")
        model = quote(request.model.removeprefix('models/'), safe='-._')
        url = f"{self.config['base_url'].rstrip('/')}/models/{model}:generateContent"
        http_request = Request(url, data=json.dumps(payload).encode('utf-8'),
                               headers={'Content-Type': 'application/json', 'x-goog-api-key': key}, method='POST')
        try:
            with self.opener(http_request, timeout=self.timeout) as response:
                data = json.loads(response.read())
        except HTTPError as error:
            try:
                raw = json.loads(error.read())
            except (ValueError, OSError):
                raw = None
            finally:
                error.close()
            kind = {400: 'invalid_request', 401: 'authentication', 403: 'permission',
                    404: 'not_found', 408: 'timeout', 429: 'rate_limit'}.get(error.code, 'provider_error')
            retryable = error.code in (408, 429) or 500 <= error.code < 600
            raise ProviderError(kind, f'Gemini HTTP {error.code}', retryable, raw) from error
        except (URLError, TimeoutError, socket.timeout, ConnectionError, HTTPException, OSError) as error:
            raise ProviderError('network', 'Gemini connection failed', True) from error
        except (ValueError, UnicodeDecodeError) as error:
            raise ProviderError('invalid_response', 'Gemini response was not JSON') from error
        return self.parse(data)

    def parse(self, data):
        try:
            if data.get('promptFeedback', {}).get('blockReason'):
                raise ProviderError('blocked', 'Gemini blocked the prompt', raw=data)
            candidate = data['candidates'][0]
            finish = candidate.get('finishReason', 'STOP')
            if finish not in ('STOP', 'MAX_TOKENS'):
                raise ProviderError('blocked' if finish in ('SAFETY', 'RECITATION') else 'invalid_response',
                                    f'Gemini stopped: {finish}', raw=data)
            content = candidate['content']
            text = ''.join(part['text'] for part in content['parts']
                           if isinstance(part.get('text'), str) and not part.get('thought'))
            calls = []
            for part in content['parts']:
                if 'functionCall' in part:
                    call = part['functionCall']
                    if not isinstance(call['name'], str) or not isinstance(call.get('args', {}), dict):
                        raise ValueError('Invalid function call')
                    calls.append(ToolCall(call['name'], call.get('args', {}), call.get('id', '')))
            if not text and not calls:
                raise ValueError('No text or function call')
            usage = data.get('usageMetadata', {})
            return LLMResponse(text=text, tool_calls=calls,
                finish_reason='length' if finish == 'MAX_TOKENS' else 'stop',
                input_tokens=usage.get('promptTokenCount'), output_tokens=usage.get('candidatesTokenCount'),
                raw_provider_response=data,
                continuation=Message('assistant', text, calls, provider_data={'gemini': content}))
        except (KeyError, IndexError, TypeError, AttributeError, ValueError) as error:
            raise ProviderError('invalid_response', 'Gemini returned an unsupported response', raw=data) from error
