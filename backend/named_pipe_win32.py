"""Small Win32 named-pipe primitives with cancellable overlapped server I/O."""

from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from functools import cache
from typing import Literal, NoReturn

_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_ERROR_FILE_NOT_FOUND = 2
_ERROR_PIPE_BUSY = 231
_ERROR_PIPE_CONNECTED = 535
_ERROR_BROKEN_PIPE = 109
_ERROR_OPERATION_ABORTED = 995
_ERROR_IO_PENDING = 997
_ERROR_INSUFFICIENT_BUFFER = 122
_TOKEN_QUERY = 0x0008
_TOKEN_GROUPS = 2
_SE_GROUP_LOGON_ID = 0xC0000000
_SDDL_REVISION_1 = 1
_PIPE_ACCESS_DUPLEX = 0x00000003
_FILE_FLAG_OVERLAPPED = 0x40000000
_PIPE_REJECT_REMOTE_CLIENTS = 0x00000008
_PIPE_UNLIMITED_INSTANCES = 255
_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_OPEN_EXISTING = 3
_WAIT_OBJECT_0 = 0
_WAIT_ABANDONED_0 = 0x00000080
_WAIT_TIMEOUT = 0x00000102
_WAIT_FAILED = 0xFFFFFFFF
_INFINITE = 0xFFFFFFFF


class _SidAndAttributes(ctypes.Structure):
    _fields_ = [("sid", wintypes.LPVOID), ("attributes", wintypes.DWORD)]


class _TokenGroups(ctypes.Structure):
    _fields_ = [("group_count", wintypes.DWORD), ("groups", _SidAndAttributes * 1)]


class _SecurityAttributes(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.DWORD),
        ("security_descriptor", wintypes.LPVOID),
        ("inherit_handle", wintypes.BOOL),
    ]


class _Overlapped(ctypes.Structure):
    _fields_ = [
        ("internal", ctypes.c_size_t),
        ("internal_high", ctypes.c_size_t),
        ("offset", wintypes.DWORD),
        ("offset_high", wintypes.DWORD),
        ("event", wintypes.HANDLE),
    ]


def _require_windows() -> None:
    if os.name != "nt":
        raise OSError("MarkdownReader Named Pipe transport requires Windows.")


@cache
def _kernel32() -> ctypes.WinDLL:
    _require_windows()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CreateEventW.argtypes = [
        wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR,
    ]
    kernel32.CreateEventW.restype = wintypes.HANDLE
    kernel32.SetEvent.argtypes = [wintypes.HANDLE]
    kernel32.SetEvent.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.WaitForMultipleObjects.argtypes = [
        wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE), wintypes.BOOL, wintypes.DWORD,
    ]
    kernel32.WaitForMultipleObjects.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    kernel32.CreateMutexW.argtypes = [
        ctypes.POINTER(_SecurityAttributes), wintypes.BOOL, wintypes.LPCWSTR,
    ]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel32.ReleaseMutex.restype = wintypes.BOOL
    kernel32.CreateNamedPipeW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
        wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(_SecurityAttributes),
    ]
    kernel32.CreateNamedPipeW.restype = wintypes.HANDLE
    kernel32.ConnectNamedPipe.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Overlapped)]
    kernel32.ConnectNamedPipe.restype = wintypes.BOOL
    kernel32.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Overlapped)]
    kernel32.CancelIoEx.restype = wintypes.BOOL
    kernel32.GetOverlappedResult.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_Overlapped), ctypes.POINTER(wintypes.DWORD),
        wintypes.BOOL,
    ]
    kernel32.GetOverlappedResult.restype = wintypes.BOOL
    kernel32.ReadFile.argtypes = [
        wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(_Overlapped),
    ]
    kernel32.ReadFile.restype = wintypes.BOOL
    kernel32.WriteFile.argtypes = [
        wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(_Overlapped),
    ]
    kernel32.WriteFile.restype = wintypes.BOOL
    kernel32.DisconnectNamedPipe.argtypes = [wintypes.HANDLE]
    kernel32.DisconnectNamedPipe.restype = wintypes.BOOL
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    return kernel32


@cache
def _advapi32() -> ctypes.WinDLL:
    _require_windows()
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [
        wintypes.LPVOID, ctypes.POINTER(wintypes.LPWSTR),
    ]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    return advapi32


def _raise_last_error() -> NoReturn:
    error = ctypes.get_last_error()
    raise OSError(error, ctypes.FormatError(error))


def _current_logon_sid() -> str:
    kernel32 = _kernel32()
    advapi32 = _advapi32()
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token),
    ):
        _raise_last_error()
    try:
        required = wintypes.DWORD()
        advapi32.GetTokenInformation(token, _TOKEN_GROUPS, None, 0, ctypes.byref(required))
        if ctypes.get_last_error() != _ERROR_INSUFFICIENT_BUFFER:
            _raise_last_error()
        groups_buffer = ctypes.create_string_buffer(required.value)
        if not advapi32.GetTokenInformation(
            token, _TOKEN_GROUPS, groups_buffer, required.value, ctypes.byref(required),
        ):
            _raise_last_error()
        groups = ctypes.cast(groups_buffer, ctypes.POINTER(_TokenGroups)).contents
        first_group = ctypes.addressof(groups) + _TokenGroups.groups.offset
        group_size = ctypes.sizeof(_SidAndAttributes)
        logon_sid: int | None = None
        for index in range(groups.group_count):
            entry = ctypes.cast(
                first_group + index * group_size, ctypes.POINTER(_SidAndAttributes),
            ).contents
            if entry.attributes & _SE_GROUP_LOGON_ID == _SE_GROUP_LOGON_ID:
                logon_sid = int(entry.sid)
                break
        if logon_sid is None:
            raise OSError("Current process token has no logon SID.")
        sid_text = wintypes.LPWSTR()
        if not advapi32.ConvertSidToStringSidW(
            ctypes.c_void_p(logon_sid), ctypes.byref(sid_text),
        ):
            _raise_last_error()
        try:
            value = sid_text.value
            if value is None:
                raise OSError("Windows did not return the logon SID string.")
            return value
        finally:
            kernel32.LocalFree(ctypes.cast(sid_text, wintypes.HLOCAL))
    finally:
        kernel32.CloseHandle(token)


def create_stop_event() -> int:
    kernel32 = _kernel32()
    handle = kernel32.CreateEventW(None, True, False, None)
    if not handle:
        _raise_last_error()
    return int(handle)


def signal_event(event_handle: int) -> None:
    if not _kernel32().SetEvent(wintypes.HANDLE(event_handle)):
        _raise_last_error()


def event_is_set(event_handle: int) -> bool:
    result = _kernel32().WaitForSingleObject(wintypes.HANDLE(event_handle), 0)
    if result == _WAIT_OBJECT_0:
        return True
    if result == _WAIT_TIMEOUT:
        return False
    _raise_last_error()


def close_handle(handle: int) -> None:
    if not _kernel32().CloseHandle(wintypes.HANDLE(handle)):
        _raise_last_error()


def _protected_security_descriptor() -> wintypes.LPVOID:
    advapi32 = _advapi32()
    logon_sid = _current_logon_sid()
    security_descriptor = wintypes.LPVOID()
    sddl = f"D:P(A;;GA;;;SY)(A;;GA;;;{logon_sid})"
    if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, _SDDL_REVISION_1, ctypes.byref(security_descriptor), None,
    ):
        _raise_last_error()
    return security_descriptor


def create_backend_mutex(mutex_name: str) -> int:
    kernel32 = _kernel32()
    security_descriptor = _protected_security_descriptor()
    security = _SecurityAttributes(
        ctypes.sizeof(_SecurityAttributes), security_descriptor, False,
    )
    try:
        handle = kernel32.CreateMutexW(ctypes.byref(security), False, mutex_name)
        if not handle:
            _raise_last_error()
        return int(handle)
    finally:
        kernel32.LocalFree(security_descriptor)


def wait_mutex(handle: int) -> Literal["acquired", "abandoned", "timeout"]:
    result = _kernel32().WaitForSingleObject(wintypes.HANDLE(handle), 0)
    if result == _WAIT_OBJECT_0:
        return "acquired"
    if result == _WAIT_ABANDONED_0:
        return "abandoned"
    if result == _WAIT_TIMEOUT:
        return "timeout"
    _raise_last_error()


def release_mutex(handle: int) -> None:
    if not _kernel32().ReleaseMutex(wintypes.HANDLE(handle)):
        _raise_last_error()


def create_server_pipe(pipe_name: str) -> int:
    kernel32 = _kernel32()
    security_descriptor = _protected_security_descriptor()
    security = _SecurityAttributes(
        ctypes.sizeof(_SecurityAttributes), security_descriptor, False,
    )
    try:
        handle = kernel32.CreateNamedPipeW(
            pipe_name,
            _PIPE_ACCESS_DUPLEX | _FILE_FLAG_OVERLAPPED,
            _PIPE_REJECT_REMOTE_CLIENTS,
            _PIPE_UNLIMITED_INSTANCES,
            4096,
            4096,
            0,
            ctypes.byref(security),
        )
        if handle == _INVALID_HANDLE_VALUE:
            _raise_last_error()
        return int(handle)
    finally:
        kernel32.LocalFree(security_descriptor)


def _new_overlapped() -> _Overlapped:
    event = _kernel32().CreateEventW(None, True, False, None)
    if not event:
        _raise_last_error()
    return _Overlapped(event=event)


def _wait_io(handle: int, overlapped: _Overlapped, stop_event: int) -> bool:
    kernel32 = _kernel32()
    wait_handles = (wintypes.HANDLE * 2)(
        wintypes.HANDLE(stop_event), overlapped.event,
    )
    result = kernel32.WaitForMultipleObjects(2, wait_handles, False, _INFINITE)
    if result == _WAIT_OBJECT_0:
        kernel32.CancelIoEx(wintypes.HANDLE(handle), ctypes.byref(overlapped))
        completed = wintypes.DWORD()
        kernel32.GetOverlappedResult(
            wintypes.HANDLE(handle), ctypes.byref(overlapped), ctypes.byref(completed), True,
        )
        return False
    if result == _WAIT_OBJECT_0 + 1:
        return True
    if result == _WAIT_FAILED:
        _raise_last_error()
    raise OSError(f"Unexpected WaitForMultipleObjects result: {result}")


def connect_server_pipe(handle: int, stop_event: int) -> bool:
    kernel32 = _kernel32()
    overlapped = _new_overlapped()
    try:
        connected = kernel32.ConnectNamedPipe(wintypes.HANDLE(handle), ctypes.byref(overlapped))
        if connected:
            return not event_is_set(stop_event)
        error = ctypes.get_last_error()
        if error == _ERROR_PIPE_CONNECTED:
            return not event_is_set(stop_event)
        if error != _ERROR_IO_PENDING:
            if error == _ERROR_OPERATION_ABORTED and event_is_set(stop_event):
                return False
            raise OSError(error, ctypes.FormatError(error))
        if not _wait_io(handle, overlapped, stop_event):
            return False
        completed = wintypes.DWORD()
        if not kernel32.GetOverlappedResult(
            wintypes.HANDLE(handle), ctypes.byref(overlapped), ctypes.byref(completed), False,
        ):
            error = ctypes.get_last_error()
            if error == _ERROR_OPERATION_ABORTED and event_is_set(stop_event):
                return False
            raise OSError(error, ctypes.FormatError(error))
        return not event_is_set(stop_event)
    finally:
        close_handle(int(overlapped.event))


def read_server_pipe(handle: int, size: int, stop_event: int) -> bytes | None:
    kernel32 = _kernel32()
    buffer = ctypes.create_string_buffer(size)
    transferred = wintypes.DWORD()
    overlapped = _new_overlapped()
    try:
        succeeded = kernel32.ReadFile(
            wintypes.HANDLE(handle), buffer, size, ctypes.byref(transferred),
            ctypes.byref(overlapped),
        )
        if not succeeded:
            error = ctypes.get_last_error()
            if error == _ERROR_BROKEN_PIPE:
                return None
            if error != _ERROR_IO_PENDING:
                if error == _ERROR_OPERATION_ABORTED and event_is_set(stop_event):
                    return None
                raise OSError(error, ctypes.FormatError(error))
            if not _wait_io(handle, overlapped, stop_event):
                return None
            if not kernel32.GetOverlappedResult(
                wintypes.HANDLE(handle), ctypes.byref(overlapped), ctypes.byref(transferred), False,
            ):
                error = ctypes.get_last_error()
                if error in {_ERROR_BROKEN_PIPE, _ERROR_OPERATION_ABORTED}:
                    return None
                raise OSError(error, ctypes.FormatError(error))
        if transferred.value == 0:
            return None
        return buffer.raw[:transferred.value]
    finally:
        close_handle(int(overlapped.event))


def write_server_pipe(handle: int, data: bytes, stop_event: int) -> bool:
    kernel32 = _kernel32()
    offset = 0
    while offset < len(data):
        chunk = data[offset:]
        buffer = ctypes.create_string_buffer(chunk)
        transferred = wintypes.DWORD()
        overlapped = _new_overlapped()
        try:
            succeeded = kernel32.WriteFile(
                wintypes.HANDLE(handle), buffer, len(chunk), ctypes.byref(transferred),
                ctypes.byref(overlapped),
            )
            if not succeeded:
                error = ctypes.get_last_error()
                if error != _ERROR_IO_PENDING:
                    if error in {_ERROR_BROKEN_PIPE, _ERROR_OPERATION_ABORTED}:
                        return False
                    raise OSError(error, ctypes.FormatError(error))
                if not _wait_io(handle, overlapped, stop_event):
                    return False
                if not kernel32.GetOverlappedResult(
                    wintypes.HANDLE(handle), ctypes.byref(overlapped),
                    ctypes.byref(transferred), False,
                ):
                    error = ctypes.get_last_error()
                    if error in {_ERROR_BROKEN_PIPE, _ERROR_OPERATION_ABORTED}:
                        return False
                    raise OSError(error, ctypes.FormatError(error))
        finally:
            close_handle(int(overlapped.event))
        if transferred.value == 0:
            return False
        offset += transferred.value
    return True


def disconnect_server_pipe(handle: int) -> None:
    kernel32 = _kernel32()
    if not kernel32.DisconnectNamedPipe(wintypes.HANDLE(handle)):
        error = ctypes.get_last_error()
        if error not in {_ERROR_BROKEN_PIPE, _ERROR_OPERATION_ABORTED}:
            raise OSError(error, ctypes.FormatError(error))


def open_client_pipe(pipe_name: str, timeout: float) -> int:
    kernel32 = _kernel32()
    deadline = time.monotonic() + timeout
    last_error = _ERROR_FILE_NOT_FOUND
    while time.monotonic() < deadline:
        handle = kernel32.CreateFileW(
            pipe_name,
            _GENERIC_READ | _GENERIC_WRITE,
            0,
            None,
            _OPEN_EXISTING,
            0,
            None,
        )
        if handle != _INVALID_HANDLE_VALUE:
            return int(handle)
        last_error = ctypes.get_last_error()
        if last_error not in {_ERROR_FILE_NOT_FOUND, _ERROR_PIPE_BUSY}:
            raise OSError(last_error, ctypes.FormatError(last_error))
        time.sleep(0.025)
    raise TimeoutError(f"Named Pipe server was not available: {pipe_name} ({last_error})")


def write_client_pipe(handle: int, data: bytes) -> None:
    kernel32 = _kernel32()
    offset = 0
    while offset < len(data):
        chunk = data[offset:]
        buffer = ctypes.create_string_buffer(chunk)
        transferred = wintypes.DWORD()
        if not kernel32.WriteFile(
            wintypes.HANDLE(handle), buffer, len(chunk), ctypes.byref(transferred), None,
        ):
            _raise_last_error()
        if transferred.value == 0:
            raise OSError("Named Pipe client write made no progress.")
        offset += transferred.value


def read_client_pipe_line(handle: int, max_bytes: int) -> bytes:
    kernel32 = _kernel32()
    pending = bytearray()
    while len(pending) <= max_bytes:
        buffer = ctypes.create_string_buffer(4096)
        transferred = wintypes.DWORD()
        if not kernel32.ReadFile(
            wintypes.HANDLE(handle), buffer, len(buffer), ctypes.byref(transferred), None,
        ):
            _raise_last_error()
        if transferred.value == 0:
            break
        pending.extend(buffer.raw[:transferred.value])
        newline = pending.find(b"\n")
        if newline >= 0:
            if newline > max_bytes:
                raise ValueError("Named Pipe response exceeds the frame limit.")
            return bytes(pending[:newline])
    raise OSError("Named Pipe closed before sending a complete response frame.")
