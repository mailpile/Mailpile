import random
import threading
import traceback
import time

import mailpile.util
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.util import *


##[ Specialized threads ]######################################################

class Cron(threading.Thread):
    """
    An instance of this class represents a cron-like worker thread
    that manages and executes tasks in regular intervals
    """

    def __init__(self, schedule, name=None, session=None):
        """
        Initializes a new Cron instance.
        Note that the thread will not be started automatically, so
        you need to call start() manually.

        Keyword arguments:
        name -- The name of the Cron instance
        session -- Currently unused
        """
        threading.Thread.__init__(self)
        self.ALIVE = False
        self.daemon = mailpile.util.TESTING
        self.name = name
        self.session = session
        self.last_run = time.time()
        self.running = 'Idle'
        self.schedule = schedule
        self.sleep = 10
        # This lock is used to synchronize
        self.lock = WorkerLock()

    def __str__(self):
        return '%s: %s (%ds)' % (threading.Thread.__str__(self),
                                 self.running, time.time() - self.last_run)

    def add_task(self, name, interval, task):
        """
        Add a task to the cron worker queue

        Keyword arguments:
        name -- The name of the task to add
        interval -- The interval (in seconds) of the task
        task    -- A task function
        """
        with self.lock:
            if name in self.schedule:
                last = self.schedule[name][3]
                status = self.schedule[name][4]
            else:
                last = time.time() - random.randint(0, interval)
                status = 'new'

            self.schedule[name] = [name, interval, task, last, status]
            self.sleep = 1
            self.__recalculateSleep()

    def __recalculateSleep(self):
        """
        Recalculate the maximum sleep delay.
        This shall be called from a lock zone only
        """
        # (Re)alculate how long we can sleep between tasks
        #    (sleep min. 1 sec, max. 61 sec)
        # --> Calculate the GCD of the task intervals
        for i in range(2, 61):  # i = second
            # Check if any scheduled task intervals are != 0 mod i
            filteredTasks = [True for task in self.schedule.values()
                             if int(task[1]) % i != 0]
            # We can sleep for i seconds if i divides all intervals
            if (len(filteredTasks) == 0):
                self.sleep = i

    def cancel_task(self, name):
        """
        Cancel a task in the current Cron instance.
        If a task with the given name does not exist,
        ignore the request.

        Keyword arguments:
        name -- The name of the task to cancel
        """
        if name in self.schedule:
            with self.lock:
                del self.schedule[name]
                self.__recalculateSleep()

    def run(self):
        """
        Thread main function for a Cron instance.

        """
        play_nice(19)  # Reduce our priority as much as possible

        # Main thread loop
        self.ALIVE = True
        while self.ALIVE and not mailpile.util.QUITTING:
            tasksToBeExecuted = []  # Contains tuples (name, func)
            now = time.time()
            # Check if any of the task is (over)due
            with self.lock:
                for task_spec in self.schedule.values():
                    name, interval, task, last, status = task_spec
                    if (last + interval) <= now:
                        tasksToBeExecuted.append((name, task))
                        self.schedule[name][4] = 'scheduled'

            # Execute the tasks
            for name, task in tasksToBeExecuted:
                # Set last_executed
                self.schedule[name][3] = time.time()
                self.schedule[name][4] = 'running'
                try:
                    self.last_run = time.time()
                    self.running = name
                    task()
                except Exception, e:
                    self.schedule[name][4] = 'FAILED'
                    self.session.ui.error(('%s failed in %s: %s'
                                           ) % (name, self.name, e))
                finally:
                    self.schedule[name][4] = 'ok'
                    self.last_run = time.time()
                    self.running = 'Finished %s' % self.running

            # Some tasks take longer than others, so use the time before
            # executing tasks as reference for the delay
            sleepTime = self.sleep
            delay = time.time() - now + sleepTime

            # Sleep for max. 1 sec to react to the quit signal in time
            while delay > 0 and self.ALIVE:
                # self.sleep might change during loop (if tasks are modified)
                # In that case, just wake up and check if any tasks need
                # to be executed
                if self.sleep != sleepTime:
                    delay = 0
                else:
                    # Sleep for max 1 second to check self.ALIVE
                    time.sleep(max(0, min(1, delay)))
                    delay -= 1

    def quit(self, session=None, join=True):
        """
        Send a signal to the current Cron instance
        to stop operation.

        Keyword arguments:
        join -- If this is True, this method will wait until
                        the Cron thread exits.
        """
        self.ALIVE = False
        if join:
            try:
                self.join()
            except RuntimeError:
                pass


class Worker(threading.Thread):

    PAUSE_DEADLINE = 2
    NICE_PRIORITY = 15

    def __init__(self, name, session, daemon=False):
        threading.Thread.__init__(self)
        self.daemon = mailpile.util.TESTING or daemon
        self.name = name or 'Worker'
        self.ALIVE = False
        self.JOBS = []
        self.JOBS_LATER = []
        self.LOCK = threading.Condition(WorkerRLock())
        self.last_run = time.time()
        self.running = 'Idle'
        self.pauses = 0
        self.session = session
        self.important = False
        self.wait_until = None

    def __str__(self):
        return ('%s: %s (%ds, jobs=%s, jobs_after=%s)'
                % (threading.Thread.__str__(self),
                   self.running,
                   time.time() - self.last_run,
                   len(self.JOBS), len(self.JOBS_LATER)))

    def add_task(self, session, name, task,
                 after=None, unique=False, first=False):
        with self.LOCK:
            if unique:
                for s, n, t in self.JOBS:
                    if n == name:
                        return
            if unique and after:
                for ts, (s, n, t) in self.JOBS_LATER:
                    if n == name:
                        return

            snt = (session, name, task)
            if first:
                self.JOBS[:0] = [snt]
            elif after:
                self.JOBS_LATER.append((after, snt))
            else:
                self.JOBS.append(snt)

            self.LOCK.notify()

    def add_unique_task(self, session, name, task, **kwargs):
        return self.add_task(session, name, task, unique=True, **kwargs)

    def do(self, session, name, task, unique=False, first=False):
        if session and session.main:
            # We run this in the foreground on the main interactive session,
            # so CTRL-C has a chance to work.
            try:
                self.pause(session, first=first)
                rv = task()
            finally:
                self.unpause(session)
        else:
            self.add_task(session, name, task, unique=unique)
            if session:
                rv = session.wait_for_task(name)
            else:
                rv = True
        return rv

    def _pause_for_user_activities(self):
        if self.wait_until is not None:
            while not self.wait_until():
                time.sleep(self.PAUSE_DEADLINE)
        play_nice_with_threads(deadline=time.time() + self.PAUSE_DEADLINE)

    def _keep_running(self, **ignored_kwargs):
        return (self.ALIVE and not mailpile.util.QUITTING)

    def _failed(self, session, name, task, e):
        self.session.ui.debug(traceback.format_exc())
        self.session.ui.error(('%s failed in %s: %s'
                               ) % (name, self.name, e))
        if session:
            session.report_task_failed(name)

    def is_idle(self):
        return (len(self.JOBS) + len(self.JOBS_LATER) < 1 and
                self.running.startswith('Finished') or
                self.running.startswith('Idle'))

    def run(self):
        play_nice(self.NICE_PRIORITY)  # Reduce priority
        self.ALIVE = True
        while self._keep_running():
            with self.LOCK:
                while len(self.JOBS) < 1:
                    if not self._keep_running(locked=True):
                        return
                    self.LOCK.wait()

            self._pause_for_user_activities()

            with self.LOCK:
                session, name, task = self.JOBS.pop(0)
                if len(self.JOBS) < 0:
                    now = time.time()
                    self.JOBS.extend(snt for ts, snt
                                     in self.JOBS_LATER if ts <= now)
                    self.JOBS_LATER = [(ts, snt) for ts, snt
                                       in self.JOBS_LATER if ts > now]

            try:
                self.last_run = time.time()
                self.running = name
                if session:
                    session.ui.mark('Starting: %s' % name)
                    session.report_task_completed(name, task())
                else:
                    task()
            except (JobPostponingException), e:
                session.ui.debug('Postponing: %s' % name)
                self.add_task(session, name, task,
                              after=time.time() + e.seconds)
            except (IOError, OSError), e:
                self._failed(session, name, task, e)
                time.sleep(1)
            except Exception, e:
                self._failed(session, name, task, e)
            finally:
                self.last_run = time.time()
                self.running = 'Finished %s' % self.running

    def pause(self, session, first=False):
        with self.LOCK:
            self.pauses += 1
            first = (self.pauses == 1)

        if first:
            def pause_task():
                session.report_task_completed('Pause', True)
                session.wait_for_task('Unpause', quiet=True)

            self.add_task(None, 'Pause', pause_task, first=first)
            session.wait_for_task('Pause', quiet=True)

    def unpause(self, session):
        with self.LOCK:
            self.pauses -= 1
            if self.pauses == 0:
                session.report_task_completed('Unpause', True)

    def die_soon(self, session=None):
        def die():
            self.ALIVE = False
        self.add_task(session, '%s shutdown' % self.name, die)

    def quit(self, session=None, join=True):
        self.die_soon(session=session)
        if join:
            try:
                self.join()
            except RuntimeError:
                pass


class ImportantWorker(Worker):

    PAUSE_DEADLINE = 0.5
    NICE_PRIORITY = 5

    def _pause_for_user_activities(self):
        # Our jobs are important, if we have too many we stop playing nice
        if len(self.JOBS) < 10:
            Worker._pause_for_user_activities(self)

    def _keep_running(self, _pass=1, locked=False):
        # This is a much more careful shutdown test, that refuses to
        # stop with jobs queued up and tries to compensate for potential
        # race conditions in our quitting code by waiting a bit and
        # then re-checking if it looks like it is time to die.
        if len(self.JOBS) > 0:
            return True
        else:
             if _pass == 2:
                 return Worker._keep_running(self)
             if self.ALIVE and not mailpile.util.QUITTING:
                 return True
             else:
                 if locked:
                     try:
                         self.LOCK.release()
                         time.sleep(1)
                     finally:
                         self.LOCK.acquire()
                 else:
                     time.sleep(1)
                 return self._keep_running(_pass=2, locked=locked)

    def _failed(self, session, name, task, e):
        # Important jobs!  Re-queue if they fail, it might be transient
        Worker._failed(self, session, name, task, e)
        self.add_unique_task(session, name, task)


class DumbWorker(Worker):
    def add_task(self, session, name, task, unique=False):
        with self.LOCK:
            return task()

    def add_unique_task(self, session, name, task, **kwargs):
        return self.add_task(session, name, task)

    def do(self, session, name, task, unique=False):
        return self.add_task(session, name, task)

    def run(self):
        pass


if __name__ == "__main__":
    import doctest
    import sys
    result = doctest.testmod(optionflags=doctest.ELLIPSIS,
                             extraglobs={'junk': {}})
    print '%s' % (result, )
    if result.failed:
        sys.exit(1)
