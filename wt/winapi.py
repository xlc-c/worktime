"""Thin ctypes layer over the Windows APIs we need.

Deliberately dependency-free (no pywin32) so the tool can run from a portable
folder without administrator rights or a compiler.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import time
from pathlib import Path

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

CF_UNICODETEXT = 13
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowTextLengthW.argtypes = [wt.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.GetLastInputInfo.argtypes = [ctypes.c_void_p]
user32.GetLastInputInfo.restype = wt.BOOL
user32.OpenClipboard.argtypes = [wt.HWND]
user32.OpenClipboard.restype = wt.BOOL
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wt.BOOL
user32.IsClipboardFormatAvailable.argtypes = [wt.UINT]
user32.IsClipboardFormatAvailable.restype = wt.BOOL
user32.GetClipboardData.argtypes = [wt.UINT]
user32.GetClipboardData.restype = wt.HANDLE

kernel32.GetTickCount64.argtypes = []
kernel32.GetTickCount64.restype = ctypes.c_ulonglong
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wt.HANDLE,
    wt.DWORD,
    wt.LPWSTR,
    ctypes.POINTER(wt.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wt.BOOL
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.CloseHandle.restype = wt.BOOL
kernel32.GlobalLock.argtypes = [wt.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wt.HGLOBAL]
kernel32.GlobalUnlock.restype = wt.BOOL
kernel32.GlobalSize.argtypes = [wt.HGLOBAL]
kernel32.GlobalSize.restype = ctypes.c_size_t


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]


BROWSER_PROCS = {
    "chrome.exe": "Chrome",
    "msedge.exe": "Edge",
    "firefox.exe": "Firefox",
    "brave.exe": "Brave",
    "opera.exe": "Opera",
    "vivaldi.exe": "Vivaldi",
    "chromium.exe": "Chromium",
}

APP_DISPLAY = {
    "excel.exe": "Excel",
    "outlook.exe": "Outlook",
    "lync.exe": "Lync",
    "winword.exe": "Word",
    "powerpnt.exe": "PowerPoint",
    "onenote.exe": "OneNote",
    "teams.exe": "Teams",
    "ms-teams.exe": "Teams",
    "notepad.exe": "Notepad",
    "explorer.exe": "Explorer",
    "acrord32.exe": "Acrobat",
    "wps.exe": "WPS",
    "et.exe": "WPS表格",
    "wpp.exe": "WPS演示",
    "code.exe": "VS Code",
    "wechat.exe": "WeChat",
    "weixin.exe": "WeChat",
}


def _process_name(pid: int) -> str:
    if not pid:
        return "unknown"
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return "unknown"
    try:
        size = wt.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
    finally:
        kernel32.CloseHandle(handle)
    return "unknown"


def display_app(proc: str) -> str:
    proc = (proc or "unknown").lower()
    if proc in BROWSER_PROCS:
        return BROWSER_PROCS[proc]
    if proc in APP_DISPLAY:
        return APP_DISPLAY[proc]
    stem = Path(proc).stem if proc else "unknown"
    return stem[:1].upper() + stem[1:] if stem else "unknown"


def is_browser(app: str) -> bool:
    return app in {"Chrome", "Edge", "Firefox", "Brave", "Opera", "Vivaldi", "Chromium"}


def get_foreground() -> dict:
    """Return app display name, process name, window title and pid."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return {"app": "unknown", "proc": "unknown", "title": "", "pid": 0, "hwnd": 0}
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 2)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    proc = _process_name(pid.value)
    return {
        "app": display_app(proc),
        "proc": proc,
        "title": buf.value,
        "pid": int(pid.value),
        "hwnd": int(hwnd),
    }


def get_idle_seconds() -> float:
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return max(0.0, (kernel32.GetTickCount64() - info.dwTime) / 1000.0)


def get_clipboard_text(retries: int = 4, delay: float = 0.03) -> str | None:
    """Best-effort Unicode text read; returns None when unavailable/empty."""
    for _ in range(max(1, retries)):
        if not user32.OpenClipboard(None):
            time.sleep(delay)
            continue
        try:
            if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                return None
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return None
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return None
            try:
                size = kernel32.GlobalSize(handle)
                # size is in bytes, UTF-16 code units; cap to avoid giant reads.
                max_chars = max(16, min(int(size // 2), 1_000_000))
                text = ctypes.wstring_at(ptr, max_chars)
                return text.split("\x00", 1)[0]
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
    return None
