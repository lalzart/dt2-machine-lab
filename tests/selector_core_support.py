"""Explicit Rust ColdFire backend for the selector's isolated instruction tests."""

import ctypes as c
import os

from unicorn import m68k_const as r


class Core:
    def __init__(self, *_architecture):
        self.lib = c.CDLL(os.environ["DT2_BUF_SELECTOR_CORE"])
        signatures = {
            "cf_new": ([], c.c_void_p),
            "cf_drop": ([c.c_void_p], None),
            "cf_map": ([c.c_void_p, c.c_uint32, c.c_uint32], None),
            "cf_write": ([c.c_void_p, c.c_uint32, c.c_void_p, c.c_size_t], c.c_int),
            "cf_read": ([c.c_void_p, c.c_uint32, c.c_void_p, c.c_size_t], c.c_int),
            "cf_reg": ([c.c_void_p, c.c_uint32, c.c_uint32, c.c_bool], c.c_uint32),
            "cf_run": ([c.c_void_p, c.c_uint32, c.c_uint32, c.c_uint32], c.c_int),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.lib, name)
            function.argtypes, function.restype = args, result
        self.ptr = self.lib.cf_new()
        self.registers = {getattr(r, f"UC_M68K_REG_D{i}"): i for i in range(8)}
        self.registers.update(
            {getattr(r, f"UC_M68K_REG_A{i}"): i + 8 for i in range(8)}
        )
        self.registers.update({r.UC_M68K_REG_PC: 16, r.UC_M68K_REG_SR: 17})

    def __del__(self):
        if getattr(self, "ptr", None):
            self.lib.cf_drop(self.ptr)

    def mem_map(self, at, size):
        self.lib.cf_map(self.ptr, at, size)

    def ctl_set_cpu_model(self, _model):
        """The compiled bridge already uses the ColdFire core."""

    def ctl_remove_cache(self, _start, _end):
        """The instruction interpreter has no translated code cache."""

    def mem_write(self, at, data):
        buf = c.create_string_buffer(bytes(data))
        if self.lib.cf_write(self.ptr, at, buf, len(data)):
            raise ValueError(f"Unmapped write {at:#x}")

    def mem_read(self, at, size):
        buf = c.create_string_buffer(size)
        if self.lib.cf_read(self.ptr, at, buf, size):
            raise ValueError(f"Unmapped read {at:#x}")
        return buf.raw

    def reg_write(self, reg, value):
        self.lib.cf_reg(self.ptr, self.registers[reg], value, True)

    def reg_read(self, reg):
        return self.lib.cf_reg(self.ptr, self.registers[reg], 0, False)

    def emu_start(self, start, end, *, count):
        status = self.lib.cf_run(self.ptr, start, end, count)
        if status:
            raise ValueError(
                f"ColdFire stopped with {status} at {self.reg_read(r.UC_M68K_REG_PC):#x}"
            )
