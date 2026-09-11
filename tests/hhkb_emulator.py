# SPDX-License-Identifier: AGPL-3.0-or-later
"""Offline Cortex-M0 fixture. Never opens a device or writes firmware.

Executes the native per-key scanner, RT/hold hooks, keymap lookup, and HID
report emitters. Only timer, capacitive read/select, and busy delay are stubbed.
GPIO is inert backing memory; startup, transport and outer main loop are absent.
"""
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_MEM_INVALID
from unicorn.arm_const import *
import hhkb_v013_generic_hold_builder_v0_2_rc2 as builder

class Machine:
    STOP=0x08000000
    def __init__(self,image):
        self.uc=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
        self.uc.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M0)
        self.uc.mem_map(0x08000000,0x20000)
        self.uc.mem_write(0x08010000,image[4:65540])
        self.uc.mem_map(0x20000000,0x5000)
        self.now=0
        self.uc.hook_add(UC_HOOK_CODE,self.hook)
        self.uc.hook_add(UC_HOOK_MEM_INVALID,self.invalid)
        # Synthetic fixture; no device dump or personal keymap is required.
        # Populate each mode bank equally to isolate release/ownership behavior.
        base=bytearray(128)
        usages={'CTRL':0xe0,'LALT':0xe2,'SPACE':0x2c,'A':4,'V':0x19,
                'FN':1,'LSHIFT':0xe1,'RSHIFT':0xe5,'LGUI':0xe3,'RALT':0xe6}
        for name,usage in usages.items():
            physical=builder.KEY_MAP[name]
            offset=image[4+0xdb68+physical]
            base[offset]=usage
        fn=bytearray(base)
        fn[image[4+0xdb68+builder.KEY_MAP['A']]]=0x50 # Fn+A = Left
        for start in [0x20000a6a,0x20000e6a,0x2000126a]:
            self.uc.mem_write(start,bytes(base)+bytes(fn))
        for addr,value in [(0x2000008c,2),(0x20000044,2)]:
            self.put(addr,value)

    def put(self,addr,value):
        self.uc.mem_write(addr,bytes([value]))

    def byte(self,addr):
        return self.uc.mem_read(addr,1)[0]

    def invalid(self,uc,access,address,size,value,data):
        raise RuntimeError(f'Unmapped access {address:#x}, PC={uc.reg_read(UC_ARM_REG_PC):#x}')

    def hook(self,uc,address,size,data):
        if address==self.STOP:
            uc.emu_stop()
        elif address==0x08012404:
            uc.reg_write(UC_ARM_REG_R0,self.now)
            uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))

    def call(self,address,**registers):
        self.uc.reg_write(UC_ARM_REG_SP,0x200024e8)
        self.uc.reg_write(UC_ARM_REG_LR,self.STOP|1)
        for k,v in registers.items():
            self.uc.reg_write(globals()['UC_ARM_REG_'+k.upper()],v)
        self.uc.emu_start(address|1,self.STOP,count=100000)
        assert self.uc.reg_read(UC_ARM_REG_PC)==self.STOP,hex(self.uc.reg_read(UC_ARM_REG_PC))
        assert self.uc.reg_read(UC_ARM_REG_SP)==0x200024e8

class Scanner(Machine):
    def __init__(self,image):
        super().__init__(image)
        self.uc.mem_map(0x50000000,0x1000) # GPIO register backing, no peripheral behavior
        self.pressed=set()
        self.put(0x20000061,0) # physical pressed-key count, updated by real scanner
        for key in range(128):
            self.uc.mem_write(0x2000076a+2*key,(500).to_bytes(2,'little'))

    def hook(self,uc,address,size,data):
        if address in (0x0801c5f4,0x0801c2ac,0x0801d904):
            if address==0x0801c2ac:
                uc.reg_write(UC_ARM_REG_R0,1000 if uc.reg_read(UC_ARM_REG_R0) in self.pressed else 0)
            uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
        else:super().hook(uc,address,size,data)

    def scan(self,now,pressed):
        self.now=now & 0xffffffff
        self.pressed=set(pressed)
        for key in range(128):
            self.put(0x200000e9,key)
            self.call(0x08014c94)

    def settle(self,now,pressed):
        # Two passes allow the stock 3 -> 2 -> 0 release debounce transition.
        self.scan(now,pressed)
        self.scan(now+1,pressed)
