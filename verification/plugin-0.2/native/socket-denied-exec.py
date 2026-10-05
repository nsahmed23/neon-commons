"""Install a child-only Linux seccomp network deny filter, then exec a verified tool.

This helper does not claim filesystem isolation. No credentials are inherited;
callers supply a complete allowlisted environment and a self-authored fixture.
"""
import ctypes
import os
import sys

lib = ctypes.CDLL("libseccomp.so.2", use_errno=True)
lib.seccomp_init.argtypes = [ctypes.c_uint32]
lib.seccomp_init.restype = ctypes.c_void_p
lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
lib.seccomp_rule_add.restype = ctypes.c_int
lib.seccomp_load.argtypes = [ctypes.c_void_p]
lib.seccomp_load.restype = ctypes.c_int
ctx = lib.seccomp_init(0x7fff0000)
assert ctx
for name in (b"socket", b"socketpair", b"connect"):
    number = lib.seccomp_syscall_resolve_name(name)
    assert number >= 0
    assert lib.seccomp_rule_add(ctx, 0x00050001, number, 0) == 0
assert lib.seccomp_load(ctx) == 0
os.execve(sys.argv[1], sys.argv[1:], dict(os.environ))
