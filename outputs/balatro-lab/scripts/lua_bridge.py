"""Run read-only analysis chunks with the Lua 5.1 DLL shipped with Balatro.

This does not start LÖVE, attach to the game, or read a player profile.
"""
from __future__ import annotations

import ctypes
from pathlib import Path


class LuaRuntime:
    def __init__(self, dll: str | Path):
        self.lib = ctypes.CDLL(str(Path(dll).resolve()))
        signatures = {
            "luaL_newstate": ([], ctypes.c_void_p),
            "luaL_openlibs": ([ctypes.c_void_p], None),
            "luaL_loadbuffer": ([ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p], ctypes.c_int),
            "lua_pcall": ([ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int], ctypes.c_int),
            "lua_tolstring": ([ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)], ctypes.c_void_p),
            "lua_settop": ([ctypes.c_void_p, ctypes.c_int], None),
            "lua_close": ([ctypes.c_void_p], None),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.lib, name)
            fn.argtypes, fn.restype = args, result
        self.state = self.lib.luaL_newstate()
        if not self.state:
            raise RuntimeError("Could not create Lua state")
        self.lib.luaL_openlibs(self.state)

    def _string(self) -> str:
        size = ctypes.c_size_t()
        ptr = self.lib.lua_tolstring(self.state, -1, ctypes.byref(size))
        return ctypes.string_at(ptr, size.value).decode("utf-8", "replace") if ptr else ""

    def execute(self, code: str, name: str = "analysis", result: bool = False):
        raw = code.encode("utf-8")
        status = self.lib.luaL_loadbuffer(self.state, raw, len(raw), name.encode("utf-8"))
        if not status:
            status = self.lib.lua_pcall(self.state, 0, 1 if result else 0, 0)
        if status:
            message = self._string()
            self.lib.lua_settop(self.state, 0)
            raise RuntimeError(message)
        value = self._string() if result else None
        self.lib.lua_settop(self.state, 0)
        return value

    def close(self):
        if self.state:
            self.lib.lua_close(self.state)
            self.state = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

