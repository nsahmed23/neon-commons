"""Allow AF_UNIX for local provider RPC; deny all other socket families."""
import ctypes
import os
import sys

class Comparison(ctypes.Structure):
    _fields_ = [('arg', ctypes.c_uint), ('op', ctypes.c_int),
                ('datum_a', ctypes.c_uint64), ('datum_b', ctypes.c_uint64)]

lib = ctypes.CDLL('libseccomp.so.2', use_errno=True)
lib.seccomp_init.argtypes = [ctypes.c_uint32]
lib.seccomp_init.restype = ctypes.c_void_p
lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
lib.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint, ctypes.POINTER(Comparison)]
lib.seccomp_rule_add_array.restype = ctypes.c_int
lib.seccomp_load.argtypes = [ctypes.c_void_p]
lib.seccomp_load.restype = ctypes.c_int
ctx = lib.seccomp_init(0x7fff0000)
assert ctx
# SCMP_CMP_NE=1, AF_UNIX=1. Socket creation for every other family is EPERM.
comparison = Comparison(0, 1, 1, 0)
for name in (b'socket', b'socketpair'):
    number = lib.seccomp_syscall_resolve_name(name)
    assert number >= 0
    assert lib.seccomp_rule_add_array(ctx, 0x00050001, number, 1, ctypes.byref(comparison)) == 0
assert lib.seccomp_load(ctx) == 0
os.execve(sys.argv[1], sys.argv[1:], dict(os.environ))
