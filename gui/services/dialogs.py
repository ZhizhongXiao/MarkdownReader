"""Native file and directory dialogs used by the GUI bridge."""

import threading
from collections.abc import Iterator
from contextlib import contextmanager


def _ask_directory(title: str) -> str:
    from tkinter import Tk
    from tkinter.filedialog import askdirectory

    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = askdirectory(title=title)
    root.destroy()
    return path if path else ""


def _pick_directory(title: str) -> str:
    """Open a folder dialog and return the picked path, or an empty string on cancel."""
    return _ask_directory(title)


class DialogInputService:
    """Serialize native dialogs and provide the GUI's file and folder inputs."""

    def __init__(self) -> None:
        # Tk keeps a process-wide default root. pywebview invokes bridge calls on separate
        # threads, so overlapping dialogs are refused instead of crossing Tk thread ownership.
        self._dialog_lock = threading.Lock()

    @contextmanager
    def one_dialog_at_a_time(self) -> Iterator[bool]:
        """Yield whether this call acquired the process-wide native-dialog slot."""
        if not self._dialog_lock.acquire(blocking=False):
            yield False
            return
        try:
            yield True
        finally:
            self._dialog_lock.release()

    def choose_directory(self, title: str) -> str | None:
        """Return None if another dialog owns the slot, or the user's path/cancel answer."""
        with self.one_dialog_at_a_time() as opened:
            if not opened:
                return None
            return _pick_directory(title)

    def select_input_files(self) -> list[str]:
        """Open a native file dialog that supports selecting multiple Markdown files."""
        from tkinter import Tk
        from tkinter.filedialog import askopenfilenames

        with self.one_dialog_at_a_time() as opened:
            if not opened:
                return []
            root = Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            paths = askopenfilenames(
                title="选择一个或多个 Markdown 文件",
                filetypes=[("Markdown", "*.md *.markdown"), ("All Files", "*.*")],
            )
            root.destroy()
            return list(paths) if paths else []

    def select_input_directory(self) -> str:
        """Open a folder dialog to select a directory of Markdown files."""
        with self.one_dialog_at_a_time() as opened:
            if not opened:
                return ""
            return _ask_directory("选择包含 Markdown 文件的目录")

    def select_output_directory(self) -> str:
        """Open a folder dialog for the conversion output directory."""
        with self.one_dialog_at_a_time() as opened:
            if not opened:
                return ""
            return _ask_directory("选择输出目录")
