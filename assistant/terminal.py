"""Terminal input and proactive output share the channel without blocking each other."""
from queue import Empty, Queue
from threading import Thread


class TerminalChannel:
    def __init__(self, notifications, reader=input, writer=print):
        self.notifications = notifications
        self.reader = reader
        self.writer = writer

    def read(self, prompt='you> '):
        # input() blocks, so keep it on a reader thread. The channel thread stays
        # available to deliver scheduler output even if the user never presses Enter.
        entered = Queue(maxsize=1)

        def read_line():
            try:
                entered.put((self.reader(prompt), None))
            except (EOFError, KeyboardInterrupt) as error:
                entered.put((None, error))
            except Exception as error:
                entered.put((None, error))

        self._drain_notifications()
        Thread(target=read_line, name='terminal-input', daemon=True).start()
        while True:
            self._drain_notifications(prompt)
            try:
                text, error = entered.get(timeout=0.1)
            except Empty:
                continue
            if error is not None:
                raise error
            return text

    def _drain_notifications(self, prompt=None):
        delivered = False
        while True:
            try:
                result = self.notifications.get_nowait()
            except Empty:
                break
            self.writer(f'\nwakeup> {result.text}\n', flush=True)
            delivered = True
        if delivered and prompt is not None:
            # Reprint the prompt. The OS keeps any partially entered input intact.
            self.writer(prompt, end='', flush=True)
