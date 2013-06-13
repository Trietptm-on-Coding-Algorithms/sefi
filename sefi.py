#!/usr/bin/env python

import argparse
import sys
import os.path
import re

from sefi_log import log
import sefi_log
import sefi_container

import distorm3
import pytrie

def search_data(segments, byte_seq, backward_search):
	bs_len = len(byte_seq)

	for segment in segments:
		log('search %d bytes starting at 0x%08x' % (len(segment.data), segment.base_addr))

		for i in range(0, len(segment.data)):
			buffer = segment.data[i:(i+bs_len)]
			if buffer == byte_seq:
				for gadget in backward_search(byte_seq, segment, i):
					yield gadget


def get_ins_seq(offset, data, arch):
	return map(
		lambda insn: insn[2],
		distorm3.Decode(offset,	data, arch)
	)

def ins_seqs_equal(a, b):
	for (x,y) in zip(a,b):
		if x != y:
			return False 

	return True

def seq_has_bad_ins(ins_seq):
	bad_ins = [
		'^DB',
		'^CALL 0x'
	]

	for ins in ins_seq:
		for reg in bad_ins:
			if re.search(reg, ins, flags = re.IGNORECASE) is not None:
				return True

	return False

def backward_search_n(byte_seq, segment, offset, arch, n):
	bs_len = len(byte_seq)
	base_addr = segment.base_addr+offset
	#t = pytrie.SortedTrie()
	gadgets = []

	if segment.data[offset:(offset+bs_len)] != byte_seq:
		raise Exception("expected %r == %r" % (segment.data[offset:(offset+bs_len)], byte_seq))

	iseq = get_ins_seq(base_addr, byte_seq, arch)
	is_len = len(iseq)

	if is_len < 1:
		raise Exception("invalid instruction sequence: %r" % byte_seq)

	log("backward search from 0x%08x for sequences ending in %r" % (base_addr, iseq))

	for i in range(1, n+1):
		data = segment.data[(offset-i):((offset-i)+bs_len+i)]
		new_seq = get_ins_seq(base_addr-i, data, arch)

		if len(new_seq) <= is_len:
			continue

		if ins_seqs_equal(new_seq[-is_len:], iseq):
			if len(new_seq) >= 2*is_len and \
					ins_seqs_equal(new_seq[:is_len], iseq):
				#if we find the same sequence preceding this one
				#we should have already looked at that so we can stop here
				break 

			if seq_has_bad_ins(new_seq):
				#log("found bad instruction, skipping...")
				continue
				
			
			gadgets.append(
				sefi_container.Gadget(
					byte_seq, base_addr,
					i, data, arch
				)
			)

	for gadget in maximal_unique_gadgets(gadgets, []):
		yield gadget

def maximal_unique_gadgets(gadgets, prefix = []):
	next_pre = {}
	arr_len = len(gadgets)
	plen = len(prefix)

	#log("maximal unique gadgets:")
	#log("gadgets: ")
	#for g in gadgets:
	#	log("  %r" % g.rev_insn_seq()[plen:])
	#log("prefix: %r" % prefix)

	if arr_len <= 1:
		#log(" => return %r" % gadgets[0].insn_seq())
		return gadgets

	for g in gadgets:
		g_seq = g.rev_insn_seq()[plen:]
		if len(g_seq) < 1:
			continue

		head, tail = g_seq[0], g_seq[1:]
		if head not in next_pre:
			next_pre[head] = [g]
		else:
			next_pre[head].append(g)

	result = []
	for head, gadgets in next_pre.items():
		#log("head:gadgets -> %r:%r\n" % (head, map(lambda g: g.rev_insn_seq(), gadgets)) )
		result += maximal_unique_gadgets(gadgets, prefix + [head])
	
	return result
	
def search_elf_for_ret_gadgets(io, seq):
	backward_search = lambda seq, seg, offset: \
		backward_search_n(seq, seg, offset, distorm3.Decode64Bits, 20)

	return search_data(elf_executable_data(io), seq, backward_search)

def elf_executable_data(io):
	from elftools.elf.elffile import ELFFile
	import sefi_elf

	eo = ELFFile(io)
	log('parsed elf file with %s sections and %s segments' % (eo.num_sections(), eo.num_segments()))

	xsegs = sefi_elf.x_segments(eo)
	for segments in sefi_elf.segment_data(eo, xsegs):
		yield segments

			
	