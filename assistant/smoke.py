"""Explicit live smoke test; never part of the offline unit-test suite."""
import argparse
import uuid
import logging

from assistant.app import Application
from assistant.config import load_config
from assistant.models import ProviderError


def main():
    parser = argparse.ArgumentParser(description='Live Gemini smoke test (spends API calls)')
    parser.add_argument('--message', default='Use current_time and tell me the time in UTC.')
    options = parser.parse_args()
    logging.getLogger('assistant').addHandler(logging.NullHandler())
    config = load_config()
    config['paths']['database'] = f'data/smoke-{uuid.uuid4().hex}.db'
    config['paths']['workspace'] = 'data/smoke-workspace'
    config['retry']['max_attempts'] = 1
    config['runtime']['request_timeout_seconds'] = 20
    app = Application(config=config)
    try:
        result = app.runtime.user_message(options.message)
        print(f'Status: {result.status}\nReply: {result.text}\nTrace: {app.store.path}')
        print('API calls:', len(app.store.rows('SELECT id FROM api_calls')))
        print('Tool calls:', len(app.store.rows('SELECT id FROM tool_calls')))
    except ProviderError as error:
        print(f'Live smoke failed: {error.kind}: {error}\nTrace: {app.store.path}')
        raise SystemExit(1) from None
    finally:
        app.close()


if __name__ == '__main__':
    main()
