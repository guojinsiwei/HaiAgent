#!/usr/bin/env node
'use strict';

/*
 * extract.js -- extract memory values from a compiled C ELF binary.
 *
 * Usage:  node extract.js /app/a.out > out.json
 *
 * Output: JSON object mapping decimal memory addresses (strings) to the
 *         32-bit little-endian integer word stored at that address.
 *
 * Model: the ELF program headers are the ground truth for the process
 * memory image.  Every PT_LOAD segment maps `p_filesz` bytes read from the
 * file at `p_offset` and `p_memsz` bytes of process memory at vaddr
 * `p_vaddr`; bytes beyond p_filesz up to p_memsz are zero (.bss).
 *
 * Address convention: Linux loads non-PIE executables at the canonical
 * base 0x400000, and their PT_LOAD p_vaddr values already include that
 * base.  A PIE (ET_DYN), by contrast, is linked with p_vaddr starting at 0
 * and is relocated by the loader.  To present the conventional process
 * image that the example output (`{"4194304": ...}` i.e. 0x400000) uses,
 * a fixed load base of 0x400000 is added for ET_DYN images so that the
 * lowest loadable address is 0x400000 (the ELF header word) in both cases.
 *
 * Caveat on that choice: the example's first key alone does NOT force this
 * convention.  Keying by `0x400000 + file_offset` reproduces it too, because
 * the first PT_LOAD of a PIE has p_offset == p_vaddr == 0 and the two only
 * diverge in segments where p_offset != p_vaddr.  Keys are therefore taken
 * from *virtual addresses* (p_vaddr + p_memsz range), which is what "memory
 * addresses" means; the file-offset rival is rejected on that ground, not
 * because the example excludes it.
 */

const fs = require('fs');

const BASE = 0x400000; // canonical Linux ELF load base

function readElf(buf) {
  if (buf.length < 64 || buf.readUInt32BE(0) !== 0x7f454c46) {
    throw new Error('not an ELF file');
  }
  const ei_class = buf[4]; // 1 = ELF32, 2 = ELF64
  const ei_data = buf[5];  // 1 = little endian, 2 = big endian
  const le = ei_data === 1;
  if (ei_data !== 1 && ei_data !== 2) {
    throw new Error('unsupported ELF data encoding: ' + ei_data);
  }

  const u16 = (o) => (le ? buf.readUInt16LE(o) : buf.readUInt16BE(o));
  const u32 = (o) => (le ? buf.readUInt32LE(o) : buf.readUInt32BE(o));
  const u64 = (o) =>
    le ? buf.readBigUInt64LE(o) : buf.readBigUInt64BE(o);

  const e_type = u16(16);
  let e_phoff, e_phentsize, e_phnum;
  if (ei_class === 2) {
    e_phoff = Number(u64(32));
    e_phentsize = u16(54);
    e_phnum = u16(56);
  } else if (ei_class === 1) {
    e_phoff = u32(28);
    e_phentsize = u16(42);
    e_phnum = u16(44);
  } else {
    throw new Error('unsupported ELF class: ' + ei_class);
  }

  const PT_LOAD = 1;
  const segments = [];
  for (let i = 0; i < e_phnum; i++) {
    const off = e_phoff + i * e_phentsize;
    if (off + e_phentsize > buf.length) break;
    let p_type, p_offset, p_vaddr, p_filesz, p_memsz;
    if (ei_class === 2) {
      p_type = u32(off + 0);
      p_offset = Number(u64(off + 8));
      p_vaddr = Number(u64(off + 16));
      p_filesz = Number(u64(off + 32));
      p_memsz = Number(u64(off + 40));
    } else {
      p_type = u32(off + 0);
      p_offset = u32(off + 4);
      p_vaddr = u32(off + 8);
      p_filesz = u32(off + 16);
      p_memsz = u32(off + 20);
    }
    if (p_type !== PT_LOAD) continue;
    segments.push({ p_offset, p_vaddr, p_filesz, p_memsz });
  }

  // ET_EXEC already has absolute vaddrs (typically starting at 0x400000);
  // ET_DYN (PIE) is linked at 0 and needs the conventional base added.
  const loadBase = e_type === 2 ? 0 : BASE;
  return { segments, loadBase };
}

function extract(buf) {
  const { segments, loadBase } = readElf(buf);
  const out = Object.create(null);

  for (const seg of segments) {
    // Process memory for this segment is [p_vaddr, p_vaddr + p_memsz).
    // 4-byte-aligned addresses relative to segment start.
    const start = seg.p_vaddr;
    const end = seg.p_vaddr + seg.p_memsz;
    for (let v = start; v + 4 <= end; v += 4) {
      const rel = v - seg.p_vaddr;
      const fileOff = seg.p_offset + rel;
      // Bytes [rel, rel+4) of the process image.  The first p_filesz bytes of
      // the segment come from the file; anything past that is zero-fill
      // (.bss).  A word may straddle the p_filesz boundary when p_filesz is
      // not 4-byte aligned, so combine the file-backed prefix with a zero
      // suffix instead of treating the whole word as zero-fill.
      const nFile = Math.max(0, Math.min(4, seg.p_filesz - rel));
      const avail = Math.max(0, Math.min(nFile, buf.length - fileOff));
      let value = 0;
      for (let b = 0; b < avail; b++) {
        value |= buf[fileOff + b] << (8 * b);
      }
      out[String(loadBase + v)] = value >>> 0;
    }
  }
  return out;
}

function main() {
  const file = process.argv[2];
  if (!file) {
    process.stderr.write('usage: node extract.js <elf-file>\n');
    process.exit(2);
  }
  const buf = fs.readFileSync(file);
  const out = extract(buf);
  process.stdout.write(JSON.stringify(out) + '\n');
}

main();
