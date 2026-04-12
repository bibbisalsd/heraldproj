import subprocess
import sys
from abc import ABC, abstractmethod


class OSPlatform(ABC):
    @abstractmethod
    def get_active_window_title(self) -> str:
        pass

    @abstractmethod
    def play_sound(self, filepath: str) -> None:
        pass

    @abstractmethod
    def get_running_processes(self) -> list[str]:
        pass


class WindowsPlatform(OSPlatform):
    def get_active_window_title(self) -> str:
        try:
            import win32gui
            window = win32gui.GetForegroundWindow()
            return win32gui.GetWindowText(window)
        except ImportError:
            return "Windows GUI missing"

    def play_sound(self, filepath: str) -> None:
        try:
            import winsound
            winsound.PlaySound(filepath, winsound.SND_FILENAME)
        except ImportError:
            pass

    def get_running_processes(self) -> list[str]:
        try:
            import win32process
            import win32gui
            processes = []
            def callback(hwnd, extra):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title:
                        processes.append(title)
            win32gui.EnumWindows(callback, None)
            return processes
        except ImportError:
            return []


class LinuxPlatform(OSPlatform):
    def get_active_window_title(self) -> str:
        try:
            result = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            return result.stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            return "xdotool missing or failed"

    def play_sound(self, filepath: str) -> None:
        try:
            subprocess.run(["aplay", "-q", filepath], check=False)
        except FileNotFoundError:
            pass

    def get_running_processes(self) -> list[str]:
        try:
            result = subprocess.run(
                ["wmctrl", "-l"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            return [line.split(maxsplit=3)[-1] for line in result.stdout.splitlines()]
        except (subprocess.SubprocessError, FileNotFoundError):
            return []


def get_platform() -> OSPlatform:
    if sys.platform == "win32":
        return WindowsPlatform()
    return LinuxPlatform()

# Global singleton for ease of use
os_platform = get_platform()
