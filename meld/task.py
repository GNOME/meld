### Copyright (C) 2002-2006 Stephen Kennedy <stevek@gnome.org>

### This program is free software; you can redistribute it and/or modify
### it under the terms of the GNU General Public License as published by
### the Free Software Foundation; either version 2 of the License, or
### (at your option) any later version.

### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.

### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

"""Classes to implement scheduling for cooperative threads.
"""

import traceback

class SchedulerBase(object):
    """Base class with common functionality for schedulers.

    Derived classes should implement the 'get_current_task' method.
    """

    def __init__(self):
        """Create a scheduler with no current tasks.
        """
        self.tasks = []
        self.callbacks = []

    def __repr__(self):
        return "%s" % self.tasks

    def connect(self, signal, action):
        assert signal == "runnable"
        try:
            self.callbacks.index(action)
        except ValueError:
            self.callbacks.append( action )

    def add_task(self, task, atfront=0):
        """Add 'task' to the task list.

        'task' may be a function, generator or scheduler.
        The task is deemed to be finished when either it returns a
        false value or raises StopIteration.
        """
        try:
            self.tasks.remove(task)
        except ValueError:
            pass

        if atfront:
            self.tasks.insert(0, task)
        else:
            self.tasks.append(task)

        for callback in self.callbacks:
            callback(self)

    def remove_task(self, task):
        """Remove 'task'.
        """
        try:
            self.tasks.remove(task)
        except ValueError:
            pass

    def remove_all_tasks(self):
        """Remove all tasks.
        """
        self.tasks = []

    def add_scheduler(self, sched):
        """Calls add_task and listens for 'sched' to emit 'runnable'.
        """
        sched.connect("runnable", lambda t : self.add_task(t))

    def remove_scheduler(self, sched):
        """Remove 'task'.
        """
        self.remove_task(sched)
        try:
            self.callbacks.remove(sched)
        except ValueError:
            pass

    def get_current_task(self):
        """Function overridden by derived classes.

        The usual implementation will be to call self._iteration(task) where
        'task' is one of self.tasks.
        """
        raise NotImplementedError("This method must be overridden by subclasses.")

    def __call__(self):
        """Check for pending tasks and run an iteration of the current task.
        """
        if len(self.tasks):
            r = self.iteration()
            if r:
                return r
        return self.tasks_pending()

    def complete_tasks(self):
        """Run all currently added tasks to completion.

        Tasks added after the call to complete_tasks are not run.
        """
        while self.tasks_pending():
            self.iteration()
        
    def tasks_pending(self):
        return len(self.tasks) != 0

    def iteration(self):
        """Perform one iteration of the current task..

        Calls self.get_current_task() to find the current task.
        Remove task from self.tasks if it is complete.
        """
        try:
            task = self.get_current_task()
        except StopIteration:
            return 0
        try:
            ret = task()
        except StopIteration:
            pass
        except Exception:
            traceback.print_exc()
        else:
            if ret:
                return ret
        self.tasks.remove(task)
        return 0


class LifoScheduler(SchedulerBase):
    """Most recently added tasks are called first.
    """
    def __init__(self):
        SchedulerBase.__init__(self)
    def get_current_task(self):
        try:
            return self.tasks[-1]
        except IndexError:
            raise StopIteration


class FifoScheduler(SchedulerBase):
    """Subtasks are called in the order they were added.
    """
    def __init__(self):
        SchedulerBase.__init__(self)
    def get_current_task(self):
        try:
            return self.tasks[0]
        except IndexError:
            raise StopIteration


class RoundRobinScheduler(SchedulerBase):
    """Each subtask is called in turn.
    """
    def __init__(self):
        SchedulerBase.__init__(self)
    def get_current_task(self):
        try:
            self.tasks.append(self.tasks.pop(0))
            return self.tasks[0]
        except IndexError:
            raise StopIteration



if __name__=="__main__":
    import time
    import random
    m = LifoScheduler()
    def timetask(t):
        while time.time() - t < 1:
            print "***"
            time.sleep(0.1)
        print "!!!"
    def sayhello(x):
        for i in range(random.randint(2,8)):
            print "hello", x
            time.sleep(0.1)
            yield 1
        print "end", x
    s = RoundRobinScheduler()
    m.add_task(s)
    h = sayhello(10).next
    #m.add_task(h)
    #m.add_task(h)
    s.add_task( sayhello(10).next )
    s.add_task( sayhello(20).next )
    s.add_task( sayhello(30).next )
    #s.add_task( sayhello(40).next )
    #s.add_task( sayhello(50).next )
    #s.add_task( sayhello(60).next )
    #m.add_task( s )
    #time.sleep(.71)
    #m.add_task( s )#sayhello(2).next )
    #m.add_task( sayhello(3).next )
    #m.add_task( lambda t=time.time() : timetask(t) )
    #m.add_task( sayhello(4).next )
    #m.add_task( sayhello(5).next )
    #m.mainloop()
    while s.tasks_pending(): s.iteration()
    time.sleep(2)
    print "***"
    #print "***"
    #m.add_task( sayhello(20).next )
    #m.add_task( s )
    #s.complete_tasks()
    #time.sleep(3)

