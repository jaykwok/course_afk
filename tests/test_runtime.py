from __future__ import annotations

import asyncio
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch

from core.runtime import close_safely, interrupt_running_async, run_child, run_operation


def process_alive(pid):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_exit_reaps_surviving_grandchild(self):
        pids = []
        with TemporaryDirectory() as tmp:
            code = "import subprocess,sys,os; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(4)'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); print(p.pid,flush=True)"
            result = await run_child([sys.executable, "-u", "-c", code], cwd=tmp, env=os.environ.copy(), on_line=lambda text: pids.append(int(text)), timeout=5)
            self.assertEqual(result, 0)
            self.assertEqual(len(pids), 1)
            self.assertFalse(process_alive(pids[0]))

    @unittest.skipUnless(os.name == "nt", "Windows Job Object guard")
    async def test_failed_job_assignment_never_starts_target_command(self):
        with TemporaryDirectory() as tmp:
            marker = Path(tmp) / "started"
            code = f"from pathlib import Path; Path({str(marker)!r}).write_text('started')"
            with patch("core.runtime.WindowsJob", side_effect=OSError("cannot own tree")):
                with self.assertRaises(OSError):
                    await run_child([sys.executable, "-c", code], cwd=tmp, env=os.environ.copy(), on_line=lambda _: None, timeout=5)
            self.assertFalse(marker.exists())

    async def test_close_finishes_before_propagating_cancellation(self):
        entered, finished = asyncio.Event(), asyncio.Event()
        async def close():
            entered.set()
            await asyncio.sleep(0.03)
            finished.set()
        task = asyncio.create_task(close_safely(close(), timeout=1))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(finished.is_set())

    async def test_cancel_reaps_child(self):
        started = asyncio.Event()
        pids = []
        def line(text):
            pids.append(int(text))
            started.set()
        with TemporaryDirectory() as tmp:
            code = "import os,time; print(os.getpid(),flush=True); time.sleep(4)"
            task = asyncio.create_task(run_child([sys.executable, "-u", "-c", code], cwd=tmp, env=os.environ.copy(), on_line=line, timeout=5))
            await asyncio.wait_for(started.wait(), 3)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertFalse(process_alive(pids[0]))

    async def test_long_stdout_line_is_drained(self):
        lines = []
        with TemporaryDirectory() as tmp:
            code = "print('x' * 70000, flush=True)"
            result = await run_child([sys.executable, "-u", "-c", code], cwd=tmp, env=os.environ.copy(), on_line=lines.append, timeout=5)
        self.assertEqual(result, 0)
        self.assertEqual(len(lines[0]), 70000)

    async def test_timeout_reaps_child(self):
        pids = []
        with TemporaryDirectory() as tmp:
            code = "import os,time; print(os.getpid(),flush=True); time.sleep(4)"
            with self.assertRaises(TimeoutError):
                await run_child([sys.executable, "-u", "-c", code], cwd=tmp, env=os.environ.copy(), on_line=lambda text: pids.append(int(text)), timeout=0.3)
        self.assertEqual(len(pids), 1)
        self.assertFalse(process_alive(pids[0]))


class OperationTests(unittest.TestCase):
    def test_repeated_cancel_does_not_interrupt_cleanup(self):
        ready, cleaning, cleaned = threading.Event(), threading.Event(), threading.Event()
        async def operation():
            ready.set()
            try:
                await asyncio.sleep(10)
            finally:
                cleaning.set()
                await asyncio.sleep(0.15)
                cleaned.set()
        def worker():
            try:
                run_operation(operation())
            except asyncio.CancelledError:
                pass
        thread = threading.Thread(target=worker)
        thread.start()
        try:
            self.assertTrue(ready.wait(3))
            self.assertTrue(interrupt_running_async())
            self.assertTrue(cleaning.wait(3))
            self.assertTrue(interrupt_running_async())
        finally:
            thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertTrue(cleaned.is_set())

    @unittest.skipUnless(os.name == "nt", "Windows Job Object integration")
    def test_application_job_reaps_descendant_after_parent_termination(self):
        root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / "child.pid"
            code = (
                "from core.runtime import protect_application_children; "
                "protect_application_children(); import subprocess,sys,time; from pathlib import Path; "
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(5)'],creationflags=subprocess.CREATE_NO_WINDOW); "
                "Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(5)"
            )
            parent = subprocess.Popen([sys.executable, "-c", code, str(pidfile)], cwd=root, creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 3
                while not pidfile.exists() and parent.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(pidfile.exists(), "isolated job owner did not start")
                child_pid = int(pidfile.read_text())
                self.assertTrue(process_alive(child_pid))
                parent.terminate()
                parent.wait(timeout=3)
                deadline = time.monotonic() + 2
                while process_alive(child_pid) and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertFalse(process_alive(child_pid))
            finally:
                if parent.poll() is None:
                    parent.terminate()
                parent.communicate(timeout=3)
