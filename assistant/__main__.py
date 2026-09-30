import argparse
import json
import logging
from logging.handlers import RotatingFileHandler

from assistant.app import Application
from assistant.config import ROOT
from assistant.terminal import TerminalChannel

HELP = '/help, /approvals, /approve ID, /deny ID, /resume RUN_ID, /runs, /jobs, /memory, /exit'


def print_approval(request):
    print(f'\napproval> #{request.id} — agent={request.agent_id}, tool={request.tool_name}\n'
          f'Arguments: {json.dumps(request.arguments, ensure_ascii=False)}\n'
          f'/approve {request.id} — approve; /deny {request.id} — deny\n', flush=True)


def print_result(app, result):
    print(f'assistant> {result.text}\n')
    # Compaction is requested only after displaying the response.
    app.after_response(result)


def main():
    parser = argparse.ArgumentParser(description='Personal Assistant V0')
    parser.add_argument('--init-only', action='store_true', help='Initialize database and profiles without API calls')
    options = parser.parse_args()
    log_path = ROOT / 'data/logs/v0.log'
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=3, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, handlers=[handler], format='%(asctime)s %(levelname)s %(name)s %(message)s')
    app = Application(on_approval=print_approval)
    try:
        if options.init_only:
            print(f'Initialized: {app.store.path}')
            return
        app.start_services()
        terminal = TerminalChannel(app.notifications)
        print(HELP)
        if app.approvals.pending():
            print('Pending approvals were restored. Use /approvals.')
        while True:
            try:
                text = terminal.read().strip()
                if not text:
                    continue
                if text == '/exit':
                    break
                if text == '/help':
                    print(HELP)
                elif text == '/approvals':
                    for row in app.approvals.pending():
                        print(row)
                elif text.startswith(('/approve ', '/deny ')):
                    command, identifier = text.split(maxsplit=1)
                    run_id = app.approvals.resolve(int(identifier), command == '/approve')
                    print_result(app, app.runtime.resume(run_id))
                elif text.startswith('/resume '):
                    print_result(app, app.runtime.resume(text.split(maxsplit=1)[1]))
                elif text == '/runs':
                    for row in app.store.rows('SELECT id,agent_id,status,error FROM runs ORDER BY rowid DESC LIMIT 20'):
                        print(row)
                elif text == '/jobs':
                    for row in app.store.rows('SELECT * FROM scheduled_jobs ORDER BY id DESC LIMIT 20'):
                        print(row)
                elif text == '/memory':
                    for row in app.store.rows('SELECT layer,content FROM memory_items ORDER BY id'):
                        print(row)
                elif text.startswith('/'):
                    print('Unknown command. ' + HELP)
                else:
                    print_result(app, app.runtime.user_message(text))
            except (EOFError, KeyboardInterrupt):
                print()
                break
            except Exception as error:
                logging.getLogger(__name__).exception('Terminal action failed')
                print(f'Error: {error}. Details: data/logs/v0.log')
    finally:
        app.close()
        handler.close()


if __name__ == '__main__':
    main()
