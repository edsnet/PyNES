import multiprocessing
from cpu.instructions import Instruction

__author__ = 'misha'

import numpy as np
import threading
import logging


log = logging.getLogger("PyNES")


class CPU(threading.Thread):
    class Memory:
        def __init__(self, console):
            self._console = console
            self._ram = [0] * 0xffff

        def write(self, address, value):
            log.debug("Memory write to address {0:#4x}".format(address))
            if address < 0 or address > 0xffff:
                raise Exception("Memory write out of bounds: {0x:#4x}".format(address))

            # RAM - Mirrored four times, so get the base address before writing.
            if address < 0x2000:
                base_address = address % 0x800
                self._ram[base_address] = np.uint8(value)

            elif 0x2000 <= address < 0x4000:
                self._console.PPU.write(address, value)

            elif 0x4000 <= address < 0x4014 or address == 0x4015:
                # pAPU registers
                log.debug("Unhandled write to pAPU registers")

            elif address == 0x4014:
                log.debug("Unhandled DMS Sprite Transfer")
                # DMA Sprite Transfer

            elif address == 0x4016 or address == 0x4017:
                log.debug("Unhandled write to controller registers")
                # Controller registers

            elif 0x6000 <= address < 0x8000:
                log.debug("Unhandled write to Save RAM")
                # Save RAM

            elif 0x8000 <= address < 0x10000:
                self._console.Cart.mem_write(address, value)

            else:
                raise Exception("Unhandled memory write to address {0:#4x}".format(address))

        def read(self, address):
            log.debug("Memory read from address {0:#4x}".format(address))
            if address < 0 or address > 0xffff:
                raise Exception("Memory read out of bounds: {0:#4x}".format(address))

            if address < 0x2000:
                # RAM
                base_address = address % 0x800
                return np.uint8(self._ram[base_address])

            elif 0x2000 <= address < 0x4000:
                # I/O Registers
                address -= 0x2000
                base = address % 8
                if base == 2:
                    return self._console.PPU.status_register()
                else:
                    log.debug("Unhandled I/O register read: {0:#4x}".format(address))

            elif 0x6000 <= address < 0x8000:
                log.debug("Unhandled read from Save RAM")

            elif 0x8000 <= address < 0x10000:
                return self._console.Cart.prg_rom[address - 0x8000]

            else:
                raise Exception("Unhandled memory read at {0:#4x}".format(address))

    class Register:
        def __init__(self, dtype):
            self._dtype = dtype
            self._value = 0xff

        def write(self, value):
            self._value = self._dtype(value)

        def read(self):
            return self._value

        def set_bit(self, bitnum, isset):
            if isset:
                self._value |= (1 << bitnum)
            else:
                self._value ^= ~(1 << bitnum)

        def increment(self, value=1):
            self._value += value

    def __init__(self, console):
        self.memory = CPU.Memory(console)
        self.registers = {'pc': CPU.Register(np.uint16), 'a': CPU.Register(np.int8), 'x': CPU.Register(np.uint8),
                          'y': CPU.Register(np.uint8), 'sp': CPU.Register(np.uint8), 'p': CPU.Register(np.uint8)}
        self.registers['p'].write(0b00100000)
        self._status_bits = {
            "carry": 0,
            "zero": 1,
            "interrupt": 2,
            "decimal": 3,
            "break": 4,
            "overflow": 6,
            "negative": 7,
        }

        self._cart = console.Cart
        self.CycleLock = multiprocessing.Lock()
        self.Cycles = multiprocessing.Value("I", 0)
        self.IRQ = multiprocessing.Value("c")
        self.IRQ.value = b'R'  # Set reset IRQ

        self._opcodes = {
            0x00: Instruction(self, Instruction.BRK, Instruction.AddressingMode.NONE, 7),
            0x01: Instruction(self, Instruction.ORA, Instruction.AddressingMode.INDIRECT_X, 6),
            0x05: Instruction(self, Instruction.ORA, Instruction.AddressingMode.ZEROPAGE, 3),
            0x06: Instruction(self, Instruction.ASL, Instruction.AddressingMode.ZEROPAGE, 3),
            0x08: Instruction(self, Instruction.PHP, Instruction.AddressingMode.NONE, 3),
            0x09: Instruction(self, Instruction.ORA, Instruction.AddressingMode.IMMEDIATE, 2),
            0x0a: Instruction(self, Instruction.ASL, Instruction.AddressingMode.ACCUMULATOR, 2),
            0x0d: Instruction(self, Instruction.ORA, Instruction.AddressingMode.ABSOLUTE, 4),
            0x0e: Instruction(self, Instruction.ASL, Instruction.AddressingMode.ABSOLUTE, 6),
            0x10: Instruction(self, Instruction.BPL, Instruction.AddressingMode.RELATIVE, 2),
            0x11: Instruction(self, Instruction.ORA, Instruction.AddressingMode.INDIRECT_Y, 5),
            0x15: Instruction(self, Instruction.ORA, Instruction.AddressingMode.ZEROPAGE_X, 4),
            0x16: Instruction(self, Instruction.ASL, Instruction.AddressingMode.ZEROPAGE_X, 6),
            0x18: Instruction(self, Instruction.CLC, Instruction.AddressingMode.NONE, 2),
            0x19: Instruction(self, Instruction.ORA, Instruction.AddressingMode.ABSOLUTE_Y, 4),
            0x1d: Instruction(self, Instruction.ORA, Instruction.AddressingMode.ABSOLUTE_X, 4),
            0x1e: Instruction(self, Instruction.ASL, Instruction.AddressingMode.ABSOLUTE_X, 7),

            0x20: Instruction(self, Instruction.JSR, Instruction.AddressingMode.ABSOLUTE, 6),
            0x21: Instruction(self, Instruction.AND, Instruction.AddressingMode.INDIRECT_X, 6),
            0x24: Instruction(self, Instruction.BIT, Instruction.AddressingMode.ZEROPAGE, 3),
            0x25: Instruction(self, Instruction.AND, Instruction.AddressingMode.ZEROPAGE, 3),
            0x26: Instruction(self, Instruction.ROL, Instruction.AddressingMode.ZEROPAGE, 5),
            0x28: Instruction(self, Instruction.PLP, Instruction.AddressingMode.NONE, 4),
            0x29: Instruction(self, Instruction.AND, Instruction.AddressingMode.IMMEDIATE, 2),
            0x2a: Instruction(self, Instruction.ROL, Instruction.AddressingMode.ACCUMULATOR, 2),
            0x2c: Instruction(self, Instruction.BIT, Instruction.AddressingMode.ABSOLUTE, 4),
            0x2d: Instruction(self, Instruction.AND, Instruction.AddressingMode.ABSOLUTE, 4),
            0x2e: Instruction(self, Instruction.ROL, Instruction.AddressingMode.ABSOLUTE, 6),
            0x30: Instruction(self, Instruction.BMI, Instruction.AddressingMode.RELATIVE, 2),
            0x31: Instruction(self, Instruction.AND, Instruction.AddressingMode.INDIRECT_Y, 5),
            0x35: Instruction(self, Instruction.AND, Instruction.AddressingMode.ZEROPAGE_X, 6),
            0x36: Instruction(self, Instruction.ROL, Instruction.AddressingMode.ZEROPAGE_X, 6),
            0x38: Instruction(self, Instruction.SEC, Instruction.AddressingMode.NONE, 2),
            0x39: Instruction(self, Instruction.AND, Instruction.AddressingMode.ABSOLUTE_Y, 4),
            0x3d: Instruction(self, Instruction.AND, Instruction.AddressingMode.ABSOLUTE_X, 4),
            0x3e: Instruction(self, Instruction.ROL, Instruction.AddressingMode.ABSOLUTE_X, 7),

            0x40: Instruction(self, Instruction.RTI, Instruction.AddressingMode.NONE, 6),
            0x41: Instruction(self, Instruction.EOR, Instruction.AddressingMode.INDIRECT_X, 6),
            0x45: Instruction(self, Instruction.EOR, Instruction.AddressingMode.ZEROPAGE, 2),
            0x46: Instruction(self, Instruction.LSR, Instruction.AddressingMode.ZEROPAGE, 5),
            0x48: Instruction(self, Instruction.PHA, Instruction.AddressingMode.NONE, 3),
            0x49: Instruction(self, Instruction.EOR, Instruction.AddressingMode.IMMEDIATE, 2),
            0x4a: Instruction(self, Instruction.LSR, Instruction.AddressingMode.ACCUMULATOR, 2),
            0x4c: Instruction(self, Instruction.JMP, Instruction.AddressingMode.ABSOLUTE, 3),
            0x4d: Instruction(self, Instruction.EOR, Instruction.AddressingMode.ABSOLUTE, 4),
            0x4e: Instruction(self, Instruction.LSR, Instruction.AddressingMode.ABSOLUTE, 6),
            0x50: Instruction(self, Instruction.BVC, Instruction.AddressingMode.RELATIVE, 2),
            0x51: Instruction(self, Instruction.EOR, Instruction.AddressingMode.INDIRECT_Y, 5),
            0x55: Instruction(self, Instruction.EOR, Instruction.AddressingMode.ZEROPAGE_X, 4),
            0x56: Instruction(self, Instruction.LSR, Instruction.AddressingMode.ZEROPAGE_X, 6),
            0x58: Instruction(self, Instruction.CLI, Instruction.AddressingMode.NONE, 2),
            0x59: Instruction(self, Instruction.EOR, Instruction.AddressingMode.ABSOLUTE_Y, 4),
            0x5d: Instruction(self, Instruction.EOR, Instruction.AddressingMode.ABSOLUTE_X, 4),
            0x5e: Instruction(self, Instruction.LSR, Instruction.AddressingMode.ABSOLUTE_X, 7),

            0x60: Instruction(self, Instruction.RTS, Instruction.AddressingMode.NONE, 6),
            0x61: Instruction(self, Instruction.ADC, Instruction.AddressingMode.INDIRECT_X, 6),
            0x65: Instruction(self, Instruction.ADC, Instruction.AddressingMode.ZEROPAGE, 3),
            0x66: Instruction(self, Instruction.ROR, Instruction.AddressingMode.ZEROPAGE, 5),
            0x68: Instruction(self, Instruction.PLA, Instruction.AddressingMode.NONE, 4),
            0x69: Instruction(self, Instruction.ADC, Instruction.AddressingMode.IMMEDIATE, 2),
            0x6a: Instruction(self, Instruction.ROR, Instruction.AddressingMode.ACCUMULATOR, 2),
            0x6c: Instruction(self, Instruction.JMP, Instruction.AddressingMode.INDIRECT, 5),
            0x6d: Instruction(self, Instruction.ADC, Instruction.AddressingMode.ABSOLUTE, 4),
            0x6e: Instruction(self, Instruction.ROR, Instruction.AddressingMode.ABSOLUTE, 6),
            0x70: Instruction(self, Instruction.BVS, Instruction.AddressingMode.RELATIVE, 2),
            0x71: Instruction(self, Instruction.ADC, Instruction.AddressingMode.INDIRECT_Y, 5),
            0x75: Instruction(self, Instruction.ADC, Instruction.AddressingMode.ZEROPAGE_X, 4),
            0x76: Instruction(self, Instruction.ROR, Instruction.AddressingMode.ZEROPAGE_X, 6),
            0x78: Instruction(self, Instruction.SEI, Instruction.AddressingMode.NONE, 2),
            0x79: Instruction(self, Instruction.ADC, Instruction.AddressingMode.ABSOLUTE_Y, 4),
            0x7d: Instruction(self, Instruction.ADC, Instruction.AddressingMode.ABSOLUTE_X, 4),
            0x7e: Instruction(self, Instruction.ROR, Instruction.AddressingMode.ABSOLUTE_X, 7),

            0x81: Instruction(self, Instruction.STA, Instruction.AddressingMode.INDIRECT_X, 6),
            0x84: Instruction(self, Instruction.STY, Instruction.AddressingMode.ZEROPAGE, 3),
            0x85: Instruction(self, Instruction.STA, Instruction.AddressingMode.ZEROPAGE, 3),
            0x86: Instruction(self, Instruction.STX, Instruction.AddressingMode.ZEROPAGE, 3),
            0x88: Instruction(self, Instruction.DEY, Instruction.AddressingMode.NONE, 2),
            0x8a: Instruction(self, Instruction.TXA, Instruction.AddressingMode.NONE, 2),
            0x8c: Instruction(self, Instruction.STY, Instruction.AddressingMode.ABSOLUTE, 4),
            0x8d: Instruction(self, Instruction.STA, Instruction.AddressingMode.ABSOLUTE, 4),
            0x8e: Instruction(self, Instruction.STX, Instruction.AddressingMode.ABSOLUTE, 4),
            0x90: Instruction(self, Instruction.BCC, Instruction.AddressingMode.RELATIVE, 2),
            0x91: Instruction(self, Instruction.STA, Instruction.AddressingMode.INDIRECT_Y, 6),
            0x94: Instruction(self, Instruction.STY, Instruction.AddressingMode.ZEROPAGE_X, 4),
            0x95: Instruction(self, Instruction.STA, Instruction.AddressingMode.ZEROPAGE_X, 4),
            0x96: Instruction(self, Instruction.STX, Instruction.AddressingMode.ZEROPAGE_Y, 4),
            0x98: Instruction(self, Instruction.TYA, Instruction.AddressingMode.NONE, 2),
            0x99: Instruction(self, Instruction.STA, Instruction.AddressingMode.ABSOLUTE_Y, 5),
            0x9a: Instruction(self, Instruction.TXS, Instruction.AddressingMode.NONE, 2),
            0x9d: Instruction(self, Instruction.STA, Instruction.AddressingMode.ABSOLUTE_X, 5),

            0xa0: Instruction(self, Instruction.LDY, Instruction.AddressingMode.IMMEDIATE, 2),
            0xa1: Instruction(self, Instruction.LDA, Instruction.AddressingMode.INDIRECT_X, 6),
            0xa2: Instruction(self, Instruction.LDX, Instruction.AddressingMode.IMMEDIATE, 2),
            0xa4: Instruction(self, Instruction.LDY, Instruction.AddressingMode.ZEROPAGE, 3),
            0xa5: Instruction(self, Instruction.LDA, Instruction.AddressingMode.ZEROPAGE, 3),
            0xa6: Instruction(self, Instruction.LDX, Instruction.AddressingMode.ZEROPAGE, 3),
            0xa8: Instruction(self, Instruction.TAY, Instruction.AddressingMode.NONE, 2),
            0xa9: Instruction(self, Instruction.LDA, Instruction.AddressingMode.IMMEDIATE, 2),
            0xaa: Instruction(self, Instruction.TAX, Instruction.AddressingMode.NONE, 2),
            0xac: Instruction(self, Instruction.LDY, Instruction.AddressingMode.ABSOLUTE, 4),
            0xad: Instruction(self, Instruction.LDA, Instruction.AddressingMode.ABSOLUTE, 4),
            0xae: Instruction(self, Instruction.LDX, Instruction.AddressingMode.ABSOLUTE, 4),
            0xb0: Instruction(self, Instruction.BCS, Instruction.AddressingMode.RELATIVE, 2),
            0xb1: Instruction(self, Instruction.LDA, Instruction.AddressingMode.INDIRECT_Y, 5),
            0xb4: Instruction(self, Instruction.LDY, Instruction.AddressingMode.ZEROPAGE_X, 4),
            0xb5: Instruction(self, Instruction.LDA, Instruction.AddressingMode.ZEROPAGE_X, 4),
            0xb6: Instruction(self, Instruction.LDX, Instruction.AddressingMode.ZEROPAGE_Y, 4),
            0xb8: Instruction(self, Instruction.CLV, Instruction.AddressingMode.NONE, 2),
            0xb9: Instruction(self, Instruction.LDA, Instruction.AddressingMode.ABSOLUTE_Y, 4),
            0xba: Instruction(self, Instruction.TSX, Instruction.AddressingMode.NONE, 2),
            0xbc: Instruction(self, Instruction.LDY, Instruction.AddressingMode.ABSOLUTE_X, 4),
            0xbd: Instruction(self, Instruction.LDA, Instruction.AddressingMode.ABSOLUTE_X, 4),
            0xbe: Instruction(self, Instruction.LDX, Instruction.AddressingMode.ABSOLUTE_Y, 4),

            0xc0: Instruction(self, Instruction.CPY, Instruction.AddressingMode.IMMEDIATE, 2),
            0xc1: Instruction(self, Instruction.CMP, Instruction.AddressingMode.INDIRECT_X, 6),
            0xc4: Instruction(self, Instruction.CPY, Instruction.AddressingMode.ZEROPAGE, 3),
            0xc5: Instruction(self, Instruction.CMP, Instruction.AddressingMode.ZEROPAGE, 3),
            0xc6: Instruction(self, Instruction.DEC, Instruction.AddressingMode.ZEROPAGE, 5),
            0xc8: Instruction(self, Instruction.INY, Instruction.AddressingMode.NONE, 2),
            0xc9: Instruction(self, Instruction.CMP, Instruction.AddressingMode.IMMEDIATE, 2),
            0xca: Instruction(self, Instruction.DEX, Instruction.AddressingMode.NONE, 2),
            0xcc: Instruction(self, Instruction.CPY, Instruction.AddressingMode.ABSOLUTE, 4),
            0xcd: Instruction(self, Instruction.CMP, Instruction.AddressingMode.ABSOLUTE, 4),
            0xce: Instruction(self, Instruction.DEC, Instruction.AddressingMode.ABSOLUTE, 6),
            0xd0: Instruction(self, Instruction.BNE, Instruction.AddressingMode.RELATIVE, 2),
            0xd1: Instruction(self, Instruction.CMP, Instruction.AddressingMode.INDIRECT_Y, 5),
            0xd5: Instruction(self, Instruction.CMP, Instruction.AddressingMode.ZEROPAGE_X, 4),
            0xd6: Instruction(self, Instruction.DEC, Instruction.AddressingMode.ZEROPAGE_X, 6),
            0xd8: Instruction(self, Instruction.CLD, Instruction.AddressingMode.NONE, 2),
            0xd9: Instruction(self, Instruction.CMP, Instruction.AddressingMode.ABSOLUTE_Y, 4),
            0xdd: Instruction(self, Instruction.CMP, Instruction.AddressingMode.ABSOLUTE_X, 4),
            0xde: Instruction(self, Instruction.DEC, Instruction.AddressingMode.ABSOLUTE_X, 7),

            0xe0: Instruction(self, Instruction.CPX, Instruction.AddressingMode.IMMEDIATE, 2),
            0xe1: Instruction(self, Instruction.SBC, Instruction.AddressingMode.INDIRECT_X, 6),
            0xe4: Instruction(self, Instruction.CPX, Instruction.AddressingMode.ZEROPAGE, 3),
            0xe5: Instruction(self, Instruction.SBC, Instruction.AddressingMode.ZEROPAGE, 3),
            0xe6: Instruction(self, Instruction.INC, Instruction.AddressingMode.ZEROPAGE, 5),
            0xe8: Instruction(self, Instruction.INX, Instruction.AddressingMode.NONE, 2),
            0xe9: Instruction(self, Instruction.SBC, Instruction.AddressingMode.IMMEDIATE, 2),
            0xea: Instruction(self, Instruction.NOP, Instruction.AddressingMode.NONE, 2),
            0xec: Instruction(self, Instruction.CPX, Instruction.AddressingMode.ABSOLUTE, 4),
            0xed: Instruction(self, Instruction.SBC, Instruction.AddressingMode.ABSOLUTE, 4),
            0xee: Instruction(self, Instruction.INC, Instruction.AddressingMode.ABSOLUTE, 6),
            0xf0: Instruction(self, Instruction.BEQ, Instruction.AddressingMode.RELATIVE, 2),
            0xf1: Instruction(self, Instruction.SBC, Instruction.AddressingMode.INDIRECT_Y, 5),
            0xf5: Instruction(self, Instruction.SBC, Instruction.AddressingMode.ZEROPAGE_X, 4),
            0xf6: Instruction(self, Instruction.INC, Instruction.AddressingMode.ZEROPAGE_X, 6),
            0xf8: Instruction(self, Instruction.SED, Instruction.AddressingMode.NONE, 2),
            0xf9: Instruction(self, Instruction.SBC, Instruction.AddressingMode.ABSOLUTE_Y, 4),
            0xfd: Instruction(self, Instruction.SBC, Instruction.AddressingMode.ABSOLUTE_X, 4),
            0xfe: Instruction(self, Instruction.INC, Instruction.AddressingMode.ABSOLUTE_X, 7)
        }

        super(CPU, self).__init__()

    def set_status(self, status, value):
        if status == "zero":
            self.registers['p'].set_bit(1, value == 0)
        elif status == "negative":
            self.registers['p'].set_bit(7, value < 0)
        else:
            self.registers['p'].set_bit(self._status_bits[status], value)

    def get_status(self, status):
        bitnum = self._status_bits[status]
        return bool(self.registers['p'].read() & (1 << bitnum))

    def execute(self, mem):
        log.debug("{0:#4x}: {1}".format(self.registers['pc'].read(), mem))
        code = mem[0]
        try:
            return self._opcodes[code](mem[1:3])
        except KeyError:
            raise Exception("Invalid opcode at {0:#4x}: {1:#4x}".format(self.registers['pc'].read(), code))

    def stack_push(self, value):
        self.registers['sp'].increment(value=-1)
        self.memory.write(0x100 + self.registers['sp'].read(), value)

    def stack_pop(self):
        val = self.memory.read(0x100 + self.registers['sp'].read())
        self.registers['sp'].increment()
        return val

    def run(self):
        while True:
            # Check IRQs
            if self.IRQ.value != b'\x00':
                log.debug("IRQ triggered with code {0}.".format(self.IRQ.value))
                self.stack_push((self.registers['pc'].read() << 8) & 0xff)
                self.stack_push((self.registers['pc'].read()) & 0xff)
                self.stack_push(self.registers['p'].read())
                self.set_status('interrupt', True)

                if self.IRQ.value == b'N':  # NMI
                    self.registers['pc'].write(self.memory.read(0xfffb) << 8 | self.memory.read(0xfffa))
                elif self.IRQ.value == b'R':  # Reset
                    self.registers['pc'].write((self.memory.read(0xfffd) << 8) | self.memory.read(0xfffc))
                elif self.IRQ.value == b'I' and not self.get_status('interrupt'):  # Maskable Interrupt
                    self.registers['pc'].write((self.memory.read(0xffff) << 8) | self.memory.read(0xfffe))

                # Clear the IRQ
                self.IRQ.value = 0

            # Fetch the next instruction, execute it, update PC and cycle counter.
            pc = self.registers['pc'].read()
            # Go directly to the cartridge prg_rom to read multiple bytes.
            pc -= 0x8000
            increment_cycles = self.execute(self._cart.prg_rom[pc:pc+3])
            self.registers['pc'].write(pc + increment_cycles)
            with self.CycleLock:
                self.Cycles.value += increment_cycles
