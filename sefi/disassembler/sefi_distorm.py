# Copyright 2013 anthony cantor
# This file is part of sefi.
# 
# sefi is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#  
# sefi is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#  
# You should have received a copy of the GNU General Public License
# along with sefi.  If not, see <http://www.gnu.org/licenses/>.
from sefi.disassembler import *
import sefi.arch
import re

try:
	import distorm3
except Exception as e:
	raise LibNotFound("error loading distorm3: %r" % e)

RET_ALL = "^RETF?( |$)"

JMP_NAMES = [
	'JO', 	'JNO', 	'JS', 	'JNS', 	'JE', 	'JZ',
	'JNE', 	'JNZ',	'JB',	'JNAE',	'JC',	'JNB',
	'JAE',	'JNC', 	'JBE',	'JNA', 	'JA',	'JNBE',
	'JL',	'JNGE',	'JGE',	'JNL',	'JLE',	'JNG',
	'JG',	'JNLE',	'JP',	'JPE',	'JNP',	'JPO',
	'JCXE',	'JECXZ', 'JMP'
]

REGISTER_NAMES = filter(
	lambda str: len(str) > 0,
	distorm3.Registers
)

JMP_REG_FMT = "^(%%s) .*(%s).*" % (
	"|".join(REGISTER_NAMES)
)

JMP_REG_ALL = JMP_REG_FMT % ("|".join(JMP_NAMES))
JMP_REG_UNCOND = JMP_REG_FMT % ('JMP')

CALL_REG_ALL = "^CALL .*(%s).*" % (
	"|".join(REGISTER_NAMES)
)

NOP_ALL = '(?:NOP(?: |$))|(?:^MOV (.+),\s*(\\1)\s*)'

class DistormInstr(Instr):

	def __init__(self, addr, data, dasm, display):
		#Instr __init__ freezes this object, so must init display_str before call to super
		self.display_str = display
		super(DistormInstr, self).__init__(addr, data, dasm)

	def __str__(self):
		return self.display_str

	def display(self):
		if self.dasm.arch == sefi.arch.x86_64:
			addr_fmt = "%016x"
		else:
			addr_fmt = "%08x"

		#[RIP+0x201ac2]
		m = re.search(
			"\[\s*(?:EIP|RIP)\s*\+\s*0x([0-9a-zA-Z]+)\s*\]",
			self.display_str,
			re.IGNORECASE
		)
		if m is not None:
			comment = (" ; 0x"+addr_fmt) % (self.addr + int(m.group(1), 16))
		else:
			comment = ""

		return self.internal_display(addr_fmt, self.display_str, comment)

	def nop(self):
		return self.match_regexp(NOP_ALL)

	def has_uncond_ctrl_flow(self):
		regs = [
			'^CALL ',
			'^JMP '
		]
		
		return self.match_regexp(*regs)

	def has_cond_ctrl_flow(self):

		return self.match_regexp(*map( 
			lambda j: '^%s ' % j,
			filter(lambda str: str != 'JMP', JMP_NAMES)
		))

	def bad(self):
		regs = [
			'^DB ',
			'^OUTS ',
			'^IN ',
			'^INS ',
			'^HLT$'
		]
	
		return self.match_regexp(*regs)

	def ret(self):
		return self.match_regexp(RET_ALL)

	def jmp_reg_uncond(self):
		return self.match_regexp(JMP_REG_UNCOND)

	def call_reg(self):
		return self.match_regexp(CALL_REG_ALL)

class DistormDasm(Disassembler):

	def __init__(self, decode_size):
		self.decode_size = decode_size
		
	def decode(self, addr, data):
		if not isinstance(data, tuple):
			raise TypeError("expected tuple of integers for data, got %s" % type(data))

		str_data = "".join([chr(x) for x in data])
		for ds_inst in distorm3.Decode(addr, str_data, self.decode_size):
			yield self.make_instr(ds_inst)

	def arch(self):
		if self.decode_size == distorm3.Decode32Bits:
			return sefi.arch.x86
		else:
			return sefi.arch.x86_64


	def make_instr(self, ds_inst):
		return DistormInstr(
			ds_inst[0],
			tuple([ord(x) for x in ds_inst[3].decode('hex')]),
			self,
			ds_inst[2]
		)


def new(arch):
	if arch == sefi.arch.x86:
		decode_size = distorm3.Decode32Bits
	elif arch == sefi.arch.x86_64:
		decode_size = distorm3.Decode64Bits
	else:
		raise ArchNotSupported("distorm3 only supports %s and %s" % (
			sefi.arch.x86,
			sefi.arch.x86_64
		))

	return DistormDasm(decode_size)
