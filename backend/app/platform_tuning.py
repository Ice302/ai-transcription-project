"""OS-level performance tweaks."""
from __future__ import annotations

import ctypes
import logging
import sys

log = logging.getLogger(__name__)

PROCESS_SET_INFORMATION = 0x0200


def disable_power_throttling(pid: int | None = None) -> bool:
    """Opt this process (or the child process ``pid``) out of Windows 11 "EcoQoS" power throttling.

    Windows throttles processes without a foreground window (the backend runs in
    a minimized console) onto efficiency cores at low clock speed. On a hybrid
    Intel CPU this made OCR go from 0.4 s to 5.3 s per frame after the first few
    seconds of work. Child processes such as ffmpeg do not inherit the opt-out, so
    each one is opted out as it starts. Measured, not guessed: see docs/PERFORMANCE.md.
    """
    if sys.platform != "win32":
        return False
    from ctypes import wintypes

    class PowerThrottlingState(ctypes.Structure):
        _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG), ("StateMask", wintypes.ULONG)]

    process_power_throttling = 4  # PROCESS_INFORMATION_CLASS.ProcessPowerThrottling
    execution_speed = 0x1  # PROCESS_POWER_THROTTLING_EXECUTION_SPEED
    state = PowerThrottlingState(1, execution_speed, 0)  # control the flag, set it to "off"
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        if pid is None:
            handle = kernel32.GetCurrentProcess()
        else:
            handle = kernel32.OpenProcess(PROCESS_SET_INFORMATION, False, pid)
            if not handle:
                return False  # already exited
        try:
            ok = bool(kernel32.SetProcessInformation(wintypes.HANDLE(handle), process_power_throttling,
                                                     ctypes.byref(state), ctypes.sizeof(state)))
        finally:
            if pid is not None:
                kernel32.CloseHandle(wintypes.HANDLE(handle))
    except Exception as exc:  # very old Windows versions lack the API
        log.debug("Could not disable power throttling: %s", exc)
        return False
    if ok and pid is None:
        log.info("Windows power throttling disabled for this process")
    return ok
