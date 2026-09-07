"""Windows test-service ownership receipts; never identify services merely by port."""

import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def creation_stamp(pid: int) -> int | None:
    if os.name != "nt":
        return None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        exit_code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)) or exit_code.value != 259:
            return None
        created, exited, system, user = (wintypes.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(system),
            ctypes.byref(user),
        ):
            return None
        return (created.dwHighDateTime << 32) | created.dwLowDateTime
    finally:
        kernel.CloseHandle(handle)


def receipt_path(role: str) -> Path:
    if role not in {"api", "web"}:
        raise ValueError("Unknown test service role")
    return ROOT / "test-results" / f"e2e-owned-{role}.json"


def terminate_owned_tree(pid: int, stamp: int) -> None:
    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("size", wintypes.DWORD),
            ("usage", wintypes.DWORD),
            ("pid", wintypes.DWORD),
            ("heap", ctypes.c_size_t),
            ("module", wintypes.DWORD),
            ("threads", wintypes.DWORD),
            ("parent", wintypes.DWORD),
            ("priority", wintypes.LONG),
            ("flags", wintypes.DWORD),
            ("exe", wintypes.WCHAR * 260),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise RuntimeError("Cannot inspect owned test service descendants")
    parents = {}
    try:
        entry = ProcessEntry()
        entry.size = ctypes.sizeof(entry)
        more = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            parents[entry.pid] = entry.parent
            more = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    owned = [(pid, stamp)]
    for parent, parent_stamp in owned:
        for child, child_parent in parents.items():
            if child_parent == parent and child != parent:
                child_stamp = creation_stamp(child)
                if child_stamp is not None and child_stamp >= parent_stamp:
                    owned.append((child, child_stamp))
    for target, expected in reversed(owned):
        handle = kernel.OpenProcess(0x101001, False, target)
        if not handle:
            continue
        try:
            if creation_stamp(target) == expected:
                if not kernel.TerminateProcess(handle, 0):
                    raise RuntimeError("Cannot terminate owned test service")
                kernel.WaitForSingleObject(handle, 5000)
        finally:
            kernel.CloseHandle(handle)


def record(role: str, pid: int) -> None:
    if os.name != "nt":
        return
    stamp = creation_stamp(pid)
    if stamp is None:
        raise RuntimeError("Cannot establish test process ownership")
    receipt = receipt_path(role)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({"pid": pid, "created": stamp}), encoding="utf-8")


def stop() -> None:
    if os.name != "nt":
        return
    for role in ("web", "api"):
        receipt = receipt_path(role)
        if not receipt.exists():
            continue
        identity = json.loads(receipt.read_text(encoding="utf-8"))
        pid = identity["pid"]
        if isinstance(pid, int) and pid > 0 and creation_stamp(pid) == identity["created"]:
            terminate_owned_tree(pid, identity["created"])
            if creation_stamp(pid) == identity["created"]:
                raise RuntimeError(f"Owned {role} test service did not stop")
        receipt.unlink(missing_ok=True)


if __name__ == "__main__":
    stop()
