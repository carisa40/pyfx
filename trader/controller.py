import threading
import itertools
from datetime import datetime, timedelta
from time import sleep

import click


class IntervalClock(object):
    def __init__(self, interval):
        self.interval = interval

    def __iter__(self):
        while True:
            # XXX: We probably want to return a datetime here
            yield datetime.utcnow()
            sleep(self.interval)


class DummyClock(object):
    def __iter__(self):
        while True:
            yield


class SimulatedClock(object):
    def __init__(self, start, stop, interval):
        self.start = start
        self.stop = stop
        self.interval = timedelta(seconds=interval)

    def __iter__(self):
        current = self.start
        while current < self.stop:
            yield current
            current += self.interval


class ControllerBase(object):
    """
    A controller class takes care to run the actions returned by the strategies
    for each clock tick. How exactly this is implemented is deferred to the
    concrete subclass.
    """
    def __init__(self, clock, broker, strategies):
        self._clock = clock
        self._broker = broker
        self._strategies = strategies

    def initialize(self, tick):
        for strategy in self._strategies:
            strategy.start(self._broker, tick)

    def run(self):
        raise NotImplementedError()

    def run_until_stopped(self):
        raise NotImplementedError()

    def stop(self):
        raise NotImplementedError()

    def execute_tick(self, tick):
        raise NotImplementedError()


class ThreadedControllerMixin(object):
    def __init__(self, *args, **kwargs):
        super(ThreadedControllerMixin, self).__init__(*args, **kwargs)
        self._stop_requested = False
        self._main_loop = None
        self._is_running = False

    def run(self):
        assert self._main_loop is None
        self._main_loop = threading.Thread(target=self._run)
        self._main_loop.start()

    def run_until_stopped(self):
        self.run()
        while self._is_running:
            try:
                sleep(1)
            except KeyboardInterrupt:
                self.stop()
                break

    def _run(self):
        self._is_running = True
        clock = iter(self._clock)
        self.initialize(next(clock))
        for tick in clock:
            if self._stop_requested:
                break
            self.execute_tick(tick)
            if self._stop_requested:
                break
        self._is_running = False

    def stop(self):
        click.secho('\nSIGINT received, shutting down cleanly...', fg='yellow')
        self._stop_requested = True
        self._main_loop.join()


class Controller(ThreadedControllerMixin, ControllerBase):
    def execute_tick(self, tick):
        operations = [strategy.tick(tick) for strategy in self._strategies]
        operations = [op for op in operations if op]
        # TODO: Add risk management/operations consolidation here
        for operation in itertools.chain(*operations):
            operation(self._broker)
