#!/usr/bin/env node
'use strict';

/*
 * extract.js -- dump the memory image described by an ELF64 x86-64 binary.
 *
 * Usage:  node extract.js /app/a.out > out.json
 *
 * The output is a single JSON object whose keys are decimal virtual memory
 * addresses (the addresses the mapping would occupy once the loader maps the
 * file at its link-time base) and whose values are the unsigned 32-bit
 * little-endian words stored at those addresses, expressed as JS integers.
 */

const fs = require('fs');

function die(msg) {
  process.stderr.write('extract.js: ' + msg + '\n');
  process.exit(1);
}

const path = process.argv[2] || '/app/a.out';

let buf;
try {
  buf = fs.readFileSync(path);
} catch (e) {
  die('cannot read ' + path + ': ' + e.message);
}

/* ------------------------------------------------------------------ *
 * Minimal ELF64 parsing
 * ------------------------------------------------------------------ */

if (buf.length < 64 || buf.readUInt32LE(0) !== 0x464c457f) {
  die('not an ELF file');
}
if (buf[4] !== 2 || buf[5] !== 1) {
  die('only little-endian ELF64 is supported');
}

const ET_DYN = 3;
const eType = buf.readUInt16LE(16);
const ePhentsize = buf.readUInt16LE(54);
const ePhnum = buf.readUInt16LE(56);
const ePhoff = Number(buf.readBigUInt64LE(32));

if (ePhnum === 0) die('no program headers');

const PT_LOAD = 1;

// Collect the PT_LOAD segments: {vaddr, off, filesz, memsz, flags}
const segs = [];
for (let i = 0; i < ePhnum; i++) {
  const o = ePhoff + i * ePhentsize;
  if (o + 56 > buf.length) break;
  const pType = buf.readUInt32LE(o);
  if (pType !== PT_LOAD) continue;
  const pFlags = buf.readUInt32LE(o + 4);
  const pOffset = Number(buf.readBigUInt64LE(o + 8));
  const pVaddr = Number(buf.readBigUInt64LE(o + 16));
  const pFilesz = Number(buf.readBigUInt64LE(o + 32));
  const pMemsz = Number(buf.readBigUInt64LE(o + 40));
  segs.push({ vaddr: pVaddr, off: pOffset, filesz: pFilesz, memsz: pMemsz, flags: pFlags });
}

if (segs.length === 0) die('no PT_LOAD segments');

/*
 * For a non-PIE executable the link-time addresses are the run-time
 * addresses.  For a PIE (ET_DYN) the loader chooses a base; we normalise the
 * image so its first loadable byte sits at the lowest link-time address.
 * When, as is usual for these binaries, p_vaddr == p_offset for every
 * segment, this is identical to the raw link-time addresses.
 */
const base = Math.min.apply(null, segs.map(s => s.vaddr));

// Highest byte of the loaded image, including .bss-style zero fill.
let imageEnd = 0;
for (const s of segs) {
  imageEnd = Math.max(imageEnd, (s.vaddr - base) + s.memsz);
}

// Backing store: image bytes, index = address - base.
const image = Buffer.alloc(imageEnd); // zero-filled, matches .bss / anon pages

for (const s of segs) {
  const dst = s.vaddr - base;
  const n = Math.min(s.filesz, Math.max(0, buf.length - s.off));
  if (n > 0) buf.copy(image, dst, s.off, s.off + n);
}

/* ------------------------------------------------------------------ *
 * Word dump
 * ------------------------------------------------------------------ */

const out = Object.create(null);
const last = imageEnd - 4;

for (let off = 0; off <= last; off += 4) {
  const addr = base + off;
  const value = image.readUInt32LE(off);
  out[String(addr)] = value;
}

process.stdout.write(JSON.stringify(out, null, 0) + '\n');
