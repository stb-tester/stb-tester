"""
A ctypes wrapper around the xxhash library included in stb-tester.  xxhash is
a non-cryptographic hash that is *fast*.  In my experiments hashing a 720p image
with xxhash takes ~242us, whereas using hash() builtin or hashlib.sha1 takes
>3ms.
"""

import binascii
import ctypes
import struct

_libxxhash = ctypes.CDLL("libxxhash.so.0")

_XXH_errorcode = ctypes.c_int
_XXH64_hash_t = ctypes.c_ulonglong
_XXH64_state_t = ctypes.c_void_p

# _XXH64_hash_t XXH64 (const void* input, size_t length,
#                      unsigned long long seed);
_libxxhash.XXH64.argtypes = [
    ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulonglong]
_libxxhash.XXH64.restype = _XXH64_hash_t

# XXH64_state_t* XXH64_createState(void);
_libxxhash.XXH64_createState.argtypes = []
_libxxhash.XXH64_createState.restype = ctypes.c_void_p

# XXH_errorcode  XXH64_freeState(XXH64_state_t* statePtr);
_libxxhash.XXH64_freeState.argtypes = [_XXH64_state_t]
_libxxhash.XXH64_freeState.restype = _XXH_errorcode

# XXH_errorcode XXH64_reset  (XXH64_state_t* statePtr, unsigned long long seed);
_libxxhash.XXH64_reset.argtypes = [_XXH64_state_t, ctypes.c_ulonglong]
_libxxhash.XXH64_reset.restype = _XXH_errorcode

# XXH_errorcode XXH64_update (
#    XXH64_state_t* statePtr, const void* input, size_t length);
_libxxhash.XXH64_update.argtypes = [
    _XXH64_state_t, ctypes.c_void_p, ctypes.c_size_t]
_libxxhash.XXH64_update.restype = _XXH_errorcode

# XXH64_hash_t  XXH64_digest (const XXH64_state_t* statePtr);
_libxxhash.XXH64_digest.argtypes = [_XXH64_state_t]
_libxxhash.XXH64_digest.restype = _XXH64_hash_t


class Xxhash64():
    __slots__ = ["_state"]
    digest_size = 16
    name = "xxhash64"

    def __init__(self, seed=0):
        self._state = _libxxhash.XXH64_createState()
        _libxxhash.XXH64_reset(self._state, seed)

    def __del__(self):
        _libxxhash.XXH64_freeState(self._state)

    def update(self, data):
        # Passing a buffer/memoryview object via ctypes is inconvenient.  See
        # http://thread.gmane.org/gmane.comp.python.devel/134936/focus=134941
        buf = memoryview(data)
        address = ctypes.c_void_p()
        length = ctypes.c_ssize_t()
        ctypes.pythonapi.PyObject_AsReadBuffer(
            ctypes.py_object(buf), ctypes.byref(address), ctypes.byref(length))
        assert length.value >= 0

        _libxxhash.XXH64_update(
            self._state, address, ctypes.c_size_t(length.value))

    def digest(self):
        return struct.pack(">Q", _libxxhash.XXH64_digest(self._state))

    def hexdigest(self):
        return binascii.hexlify(self.digest()).decode("utf-8")
