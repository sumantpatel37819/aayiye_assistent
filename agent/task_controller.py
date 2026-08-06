"""
agent/task_controller.py — Centralized task execution controller for Pause, Resume, Stop, and Progress Tracking.
"""

import threading

class TaskController:
    def __init__(self):
        self._pause_event = threading.Event()
        self._pause_event.set()  # True = running, False = paused
        self._cancel_flag = False
        self.current_task = ""
        self.current_index = 0
        self.total_count = 0
        self.current_item_name = ""
        self._callbacks = []

    def register_callback(self, callback):
        """Register GUI progress update callback."""
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def _notify(self, status: str):
        for cb in self._callbacks:
            try:
                cb(self.current_task, self.current_index, self.total_count, self.current_item_name, status)
            except Exception:
                pass

    def pause(self):
        self._pause_event.clear()
        print("  ⏸️ TASK CONTROL: Pause requested. Processing will pause after current item...")
        self._notify("PAUSED_REQUESTED")

    def resume(self):
        self._pause_event.set()
        print("  ▶️ TASK CONTROL: Task resumed.")
        self._notify("RUNNING")

    def stop(self):
        self._cancel_flag = True
        self._pause_event.set()  # Unblock if paused so it can exit loop cleanly
        print("  ⏹️ TASK CONTROL: Task stop requested.")
        self._notify("STOPPED")

    def reset(self, task_name: str = "", total: int = 0):
        self._pause_event.set()
        self._cancel_flag = False
        self.current_task = task_name
        self.current_index = 0
        self.total_count = total
        self.current_item_name = ""
        self._notify("STARTED")

    def is_paused(self) -> bool:
        return not self._pause_event.is_set()

    def is_cancelled(self) -> bool:
        return self._cancel_flag

    def check_point(self, current_index: int, total_count: int, item_name: str, task_name: str = "") -> bool:
        """
        Call this before processing each item.
        Returns False if task was cancelled/stopped.
        Waits if task is paused.
        """
        self.current_index = current_index
        self.total_count = total_count
        self.current_item_name = item_name
        if task_name:
            self.current_task = task_name

        if self._cancel_flag:
            print(f"  ⏹️ Task '{self.current_task}' stopped by user.")
            self._notify("STOPPED")
            return False

        if not self._pause_event.is_set():
            print(f"  ⏸️ Task '{self.current_task}' paused at [{current_index}/{total_count}] '{item_name}'. Waiting for resume...")
            self._notify("PAUSED")
            self._pause_event.wait()
            if self._cancel_flag:
                print(f"  ⏹️ Task '{self.current_task}' stopped during pause.")
                self._notify("STOPPED")
                return False
            print(f"  ▶️ Task '{self.current_task}' resuming at [{current_index}/{total_count}] '{item_name}'...")

        self._notify("RUNNING")
        return True

# Shared global controller instance
task_controller = TaskController()
