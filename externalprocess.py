from multiprocessing import Process, Manager
import subprocess
from ctypes import c_char_p
import os
import time
from logger import _logger
from mail import send_mail


class ExternalProcess(object):
    """Control an external process and monitor if works properly"""

    _counter = 0
    _instance = []
    def __init__(self, args, name=''):
        self.__class__._counter += 1
        self.__class__._instance.append(self)
        self.name = name
        self.args = args

    def keep(self):
        """Should always keep running"""
        self.pid.value = os.getpid()
        _logger.info(f"Process '{self.name}' (PID: {self.pid.value}) starts")

    def launch(self):
        """Process Launcher. Monitor after launching the external process"""
        self.pid = Manager().Value('i', 0) # a shared value
        self.errormsg = Manager().Value(c_char_p, "")
        self.p = Process(target=self.keep, args=())
        self.p.start()

    @classmethod
    def monitor_all(cls):
        """Monitor all external processes held by the class. If any process halts, notify the admin"""
        is_halt = {}
        while True:
            time.sleep(10)
            for iobj, obj in enumerate(cls._instance):
                obj.p.join(timeout=0)
                if not obj.p.is_alive() and iobj not in is_halt:
                    is_halt[iobj] = True
                    subject = f"Wiki error: process '{obj.name}' (PID: {obj.pid.value}) is halted"
                    _logger.error(subject+': '+obj.errormsg.value)
                    send_mail(subject=subject, text=obj.errormsg.value, args=obj.args)
            if len(is_halt) == len(cls._instance):
                _logger.error('End of class: all processes are halted')
                break
