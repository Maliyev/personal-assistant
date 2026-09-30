import unittest
from queue import Queue
from threading import Event, Thread

from assistant.runtime import RunResult
from assistant.terminal import TerminalChannel


class TerminalTests(unittest.TestCase):
    def test_wakeup_is_displayed_while_input_is_still_blocked(self):
        notifications = Queue()
        reading, release, shown = Event(), Event(), Event()
        output, entered = [], []

        def reader(prompt):
            reading.set()
            if not release.wait(5):
                raise TimeoutError('Test reader was not released')
            return 'partially entered text'

        def writer(text, **options):
            output.append(text)
            if 'wakeup> reminder' in text:
                shown.set()

        channel = TerminalChannel(notifications, reader, writer)
        thread = Thread(target=lambda: entered.append(channel.read()), daemon=True)
        thread.start()
        try:
            self.assertTrue(reading.wait(2))
            notifications.put(RunResult('reminder', 'run', 'session'))
            self.assertTrue(shown.wait(2))
            self.assertTrue(thread.is_alive())
            self.assertEqual(entered, [])
        finally:
            release.set()
            thread.join(timeout=2)
        self.assertEqual(entered, ['partially entered text'])
        self.assertEqual(sum('wakeup> reminder' in line for line in output), 1)

    def test_eof_is_forwarded_to_the_channel(self):
        def reader(prompt):
            raise EOFError
        with self.assertRaises(EOFError):
            TerminalChannel(Queue(), reader).read()
