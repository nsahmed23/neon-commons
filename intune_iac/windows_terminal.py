"""Inactive native WinConsole adapter; presentation conveys no operation authority.

No host profile selects this module. Actual Windows console and paste behavior
must be qualified separately; injected API records are laboratory evidence only.
"""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
import ctypes as C
import os
import sys

from .io import AppError

SCHEMA = 'intune-native-console/1'
DWORD = C.c_uint32
WORD = C.c_uint16
SHORT = C.c_int16
BOOL = C.c_int32
HANDLE = C.c_void_p
INPUT_HANDLE = DWORD(-10).value
OUTPUT_HANDLE = DWORD(-11).value
CTRL = 0x0004 | 0x0008
ALT = 0x0001 | 0x0002
MAX_REPEAT = 64


class COORD(C.Structure):
    _fields_ = [('X', SHORT), ('Y', SHORT)]


class SMALL_RECT(C.Structure):
    _fields_ = [('Left', SHORT), ('Top', SHORT), ('Right', SHORT), ('Bottom', SHORT)]


class SCREEN_BUFFER_INFO(C.Structure):
    _fields_ = [('size', COORD), ('cursor', COORD), ('attributes', WORD),
                ('window', SMALL_RECT), ('maximum', COORD)]


class KEY_EVENT(C.Structure):
    _fields_ = [('down', BOOL), ('repeat', WORD), ('virtual_key', WORD), ('scan', WORD),
                ('unicode', WORD), ('control', DWORD)]


class EVENT_DATA(C.Union):
    _fields_ = [('key', KEY_EVENT), ('size', COORD), ('padding', C.c_ubyte * 16)]


class INPUT_RECORD(C.Structure):
    _fields_ = [('kind', WORD), ('event', EVENT_DATA)]


def _fail(code):
    raise AppError(code, 'The inactive native console contract was not established.') from None


class _Win32:
    def __init__(self):
        if os.name != 'nt' or sys.platform != 'win32' or not hasattr(C, 'WinDLL') or C.sizeof(C.c_void_p) != 8:
            _fail('native_console_host_unsupported')
        self.k = C.WinDLL('kernel32.dll', use_last_error=True, winmode=0x800)
        signatures = {
            'GetStdHandle': ([DWORD], HANDLE),
            'GetConsoleMode': ([HANDLE, C.POINTER(DWORD)], BOOL),
            'SetConsoleMode': ([HANDLE, DWORD], BOOL),
            'WaitForSingleObject': ([HANDLE, DWORD], DWORD),
            'ReadConsoleInputW': ([HANDLE, C.POINTER(INPUT_RECORD), DWORD, C.POINTER(DWORD)], BOOL),
            'GetConsoleScreenBufferInfo': ([HANDLE, C.POINTER(SCREEN_BUFFER_INFO)], BOOL),
            'WriteConsoleW': ([HANDLE, C.c_void_p, DWORD, C.POINTER(DWORD), C.c_void_p], BOOL),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.k, name); function.argtypes = arguments; function.restype = result

    def handles(self):
        values = (self.k.GetStdHandle(INPUT_HANDLE), self.k.GetStdHandle(OUTPUT_HANDLE))
        if any(value in (None, 0, C.c_void_p(-1).value) for value in values):
            _fail('native_console_handle_unavailable')
        return values

    def mode(self, handle):
        result = DWORD()
        if not self.k.GetConsoleMode(handle, C.byref(result)):
            _fail('native_console_redirected_or_unsupported')
        return result.value

    def set_mode(self, handle, value):
        if not self.k.SetConsoleMode(handle, value):
            _fail('native_console_mode_failed')
        if self.mode(handle) != value:
            _fail('native_console_mode_readback_failed')

    def wait(self, handle, timeout_ms):
        result = self.k.WaitForSingleObject(handle, timeout_ms)
        if result == 0: return True
        if result == 258: return False
        _fail('native_console_wait_failed')

    def read(self, handle):
        record, count = INPUT_RECORD(), DWORD()
        if not self.k.ReadConsoleInputW(handle, C.byref(record), 1, C.byref(count)) or count.value != 1:
            _fail('native_console_read_failed')
        if record.kind == 1:
            key = record.event.key
            return {'kind': 'key', 'down': bool(key.down), 'repeat': key.repeat,
                    'virtual_key': key.virtual_key, 'unicode': key.unicode, 'control': key.control}
        return {'kind': 'resize' if record.kind == 4 else 'ignored'}

    def size(self, handle):
        result = SCREEN_BUFFER_INFO()
        if not self.k.GetConsoleScreenBufferInfo(handle, C.byref(result)):
            _fail('native_console_size_failed')
        width = result.window.Right - result.window.Left + 1
        height = result.window.Bottom - result.window.Top + 1
        if width <= 0 or height <= 0: _fail('native_console_size_invalid')
        return max(12, min(200, width)), max(8, min(100, height))

    def write(self, handle, text):
        if type(text) is not str or len(text) > 1024 * 1024:
            _fail('native_console_output_bound')
        try: data = text.encode('utf-16-le', errors='strict')
        except UnicodeError: _fail('native_console_invalid_unicode')
        offset = 0
        while offset < len(data):
            raw = data[offset:offset + 8192]
            # Avoid splitting a UTF-16 surrogate pair across writes.
            if len(raw) < len(data) - offset and 0xD800 <= int.from_bytes(raw[-2:], 'little') <= 0xDBFF:
                raw = raw[:-2]
            buffer = C.create_string_buffer(raw); count = DWORD()
            if not self.k.WriteConsoleW(handle, buffer, len(raw) // 2, C.byref(count), None):
                _fail('native_console_write_failed')
            if not 0 < count.value <= len(raw) // 2:
                _fail('native_console_partial_write_invalid')
            offset += count.value * 2
        return len(text)


class _KeyReader:
    NAVIGATION = {0x25:'left', 0x26:'up', 0x27:'right', 0x28:'down', 0x21:'pageup',
                  0x22:'pagedown', 0x24:'home', 0x23:'end', 0x2E:'delete', 0x1B:'escape',
                  0x08:'backspace', 0x09:'tab'}
    def __init__(self, api, handle):
        self.api, self.handle = api, handle
        self.pending = deque(); self.high_surrogate = None

    def _decode(self, event):
        if event['kind'] == 'resize': return 'redraw', 1
        if event['kind'] != 'key' or not event.get('down'): return 'ignored', 1
        repeat = event['repeat']; key = event['virtual_key']; value = event['unicode']; modifiers = event['control']
        if (type(repeat) is not int or not 1 <= repeat <= MAX_REPEAT or type(value) is not int
                or not 0 <= value <= 0xFFFF or type(key) is not int or not 0 <= key <= 0xFFFF
                or type(modifiers) is not int or modifiers < 0 or modifiers > 0xFFFF):
            self.high_surrogate = None; return 'ignored', 1
        control = bool(modifiers & CTRL)
        if modifiers & ALT:
            self.high_surrogate = None; return 'ignored', 1  # AltGr/IME qualification is deliberately pending.
        if key == 0x0D:
            self.high_surrogate = None
            return ('submit' if control else 'enter'), 1
        if control:
            self.high_surrogate = None
            return {0x43:'interrupt', 0x44:'eof', 0x55:'clear', 0x4C:'redraw'}.get(key, 'ignored'), 1
        if key in self.NAVIGATION:
            self.high_surrogate = None; return self.NAVIGATION[key], repeat
        if 0xD800 <= value <= 0xDBFF:
            self.high_surrogate = value; return 'ignored', 1
        if 0xDC00 <= value <= 0xDFFF:
            high, self.high_surrogate = self.high_surrogate, None
            if high is None: return 'ignored', 1
            return ('text', chr(0x10000 + ((high - 0xD800) << 10) + value - 0xDC00)), repeat
        self.high_surrogate = None
        if value < 32 or value == 127: return 'ignored', 1
        return ('text', chr(value)), repeat

    def read(self):
        if self.pending: return self.pending.popleft()
        if not self.api.wait(self.handle, 150): return None
        result, count = self._decode(self.api.read(self.handle))
        self.pending.extend([result] * (count - 1))
        return result


class NativeConsole:
    """Exact native console session; no fallback or service authority."""
    submission_key = 'submit'
    def __init__(self):
        self._initialize(_Win32())

    def _initialize(self, api):
        self.api = api; self.input_handle, self.output_handle = api.handles()
        self.original_input = api.mode(self.input_handle); self.original_output = api.mode(self.output_handle)
        self.key_reader = _KeyReader(api, self.input_handle); self.active = False

    def size(self): return self.api.size(self.output_handle)
    def write(self, text): return self.api.write(self.output_handle, text)
    def flush(self): return None  # WriteConsoleW is synchronous; no buffered stream is owned.
    def isatty(self): return True

    @contextmanager
    def session(self):
        if self.active: _fail('native_console_session_reentry')
        if (self.api.mode(self.input_handle) != self.original_input
                or self.api.mode(self.output_handle) != self.original_output):
            _fail('native_console_mode_changed_before_session')
        from .workbench_tui import ANSI_START, ANSI_END
        self.active = True; entered = False
        # Remove processed/line/echo/quick-edit/VT input, retain window events.
        requested_input = (self.original_input | 0x0080 | 0x0008) & ~(0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0040 | 0x0200)
        requested_output = self.original_output | 0x0001 | 0x0004
        try:
            self.api.set_mode(self.input_handle, requested_input)
            self.api.set_mode(self.output_handle, requested_output)
            entered = True; self.write(ANSI_START)
            yield self
        finally:
            primary = sys.exc_info()[1]; failures = []
            if entered:
                try: self.write(ANSI_END)
                except BaseException as error: failures.append(type(error).__name__ + ':display')
            for handle, mode, label in [(self.output_handle, self.original_output, 'output_mode'),
                                        (self.input_handle, self.original_input, 'input_mode')]:
                try: self.api.set_mode(handle, mode)
                except BaseException as error: failures.append(type(error).__name__ + ':' + label)
            self.active = False
            if failures:
                if primary is not None:
                    primary.native_console_cleanup_failures = failures
                    if hasattr(primary, 'add_note'): primary.add_note('Native console restoration also failed: ' + ', '.join(failures))
                else: _fail('native_console_cleanup_failed')
