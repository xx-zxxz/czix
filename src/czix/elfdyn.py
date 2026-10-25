"""Minimal ELF reader for dynamic symbols & DT_NEEDED — stdlib only.

Covers ELF64 & ELF32, little-endian (x86_64, arm64, armv7). Enough for
mapping an Android APK's native API surface: imported (UND) symbols from
bionic/NDK and its DT_NEEDED libraries. Not a general-purpose elffile.
"""
import struct
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

ELF_MAGIC = b"\x7fELF"
SHT_DYNSYM = 11
SHT_DYNAMIC = 6
DT_NULL, DT_NEEDED, DT_STRTAB = 0, 1, 5

MACHINES = {3: "x86", 40: "arm", 62: "x86_64", 183: "arm64"}


class ElfError(ValueError):
    pass


def parse(data: bytes) -> dict:
    """Parse an ELF image.

    Returns {"class": 32|64, "machine": str, "needed": [...],
             "imported": [...], "exported": [...]}.
    """
    if len(data) < 0x40 or data[:4] != ELF_MAGIC:
        raise ElfError("not an ELF image")
    ei_class, ei_data = data[4], data[5]
    if ei_class not in (1, 2):
        raise ElfError(f"unsupported ELF class {ei_class}")
    if ei_data != 1:
        raise ElfError("big-endian ELF not supported")
    en = "<"

    if ei_class == 2:  # ELF64 header
        (e_type, e_machine, _ver, _entry, _phoff, e_shoff, _flags, _ehsize,
         _phentsize, _phnum, e_shentsize, e_shnum, _shstrndx) = \
            struct.unpack_from(en + "HHIQQQIHHHHHH", data, 16)
        e_shentsize = e_shentsize or 64
    else:  # ELF32
        (e_type, e_machine, _ver, _entry, _phoff, e_shoff, _flags, _ehsize,
         _phentsize, _phnum, e_shentsize, e_shnum, _shstrndx) = \
            struct.unpack_from(en + "HHIIIIIHHHHHH", data, 16)
        e_shentsize = e_shentsize or 40

    sh_fmt = "IIQQQQIIQQ" if ei_class == 2 else "IIIIIIIIII"
    sym_fmt = "IBBHQQ" if ei_class == 2 else "IIIBBH"

    sections = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        raw = struct.unpack_from(en + sh_fmt, data, off)
        (sh_name, sh_type, _fl, sh_addr, sh_off, sh_size, sh_link, _info,
         _align, sh_entsize) = raw
        sections.append({"name_off": sh_name, "type": sh_type,
                         "addr": sh_addr, "offset": sh_off, "size": sh_size,
                         "link": sh_link, "entsize": sh_entsize})

    out = {"class": ei_class * 32, "machine": MACHINES.get(e_machine, str(e_machine)),
           "needed": [], "imported": [], "exported": []}

    # ---- .dynamic: DT_NEEDED via DT_STRTAB → file offset via section table
    for sec in sections:
        if sec["type"] != SHT_DYNAMIC:
            continue
        entsize = sec["entsize"] or (16 if ei_class == 2 else 8)
        n = sec["size"] // entsize
        dyn = []
        for i in range(n):
            raw = data[sec["offset"] + i * entsize:
                       sec["offset"] + (i + 1) * entsize]
            d_tag, d_val = struct.unpack(en + ("QQ" if ei_class == 2 else "II"), raw)
            if d_tag == DT_NULL:
                break
            dyn.append((d_tag, d_val))
        str_vaddr = next((v for t, v in dyn if t == DT_STRTAB), None)
        stroff = None
        for s2 in sections:
            if s2["size"] and s2["addr"] <= (str_vaddr or 0) < s2["addr"] + s2["size"]:
                stroff = s2["offset"] + (str_vaddr - s2["addr"])
                break
        if stroff is not None:
            out["needed"] = [_sym(data[stroff:], v) for t, v in dyn if t == DT_NEEDED]
        break

    # ---- .dynsym: UND = imported, else exported
    for sec in sections:
        if sec["type"] != SHT_DYNSYM:
            continue
        if sec["link"] >= len(sections):
            continue
        link = sections[sec["link"]]
        if not link["size"]:
            continue
        strtab = data[link["offset"]:link["offset"] + link["size"]]
        entsize = sec["entsize"] or (24 if ei_class == 2 else 16)
        for i in range(sec["size"] // entsize):
            raw = data[sec["offset"] + i * entsize:
                       sec["offset"] + (i + 1) * entsize]
            if ei_class == 2:
                st_name, _info, _o, st_shndx, _val, _size = \
                    struct.unpack(en + sym_fmt, raw)
            else:
                st_name, _val, _size, _info, _o, st_shndx = \
                    struct.unpack(en + sym_fmt, raw)
            if st_name == 0:
                continue
            name = _sym(strtab, st_name)
            if not name:
                continue
            bucket = out["imported"] if st_shndx == 0 else out["exported"]
            bucket.append(name)
        break
    return out


def _sym(strtab: bytes, off: int) -> str:
    end = strtab.find(b"\x00", off)
    return strtab[off:end].decode("utf-8", "replace")


def from_apk(apk_path: Path, predicate=lambda n: True) -> list[dict]:
    """Parse every matching lib/*.so inside an APK/bundle zip."""
    results = []
    with zipfile.ZipFile(apk_path) as z:
        for name in z.namelist():
            if name.startswith("lib/") and name.endswith(".so") and predicate(name):
                try:
                    info = parse(z.read(name))
                except (ElfError, zipfile.BadZipFile, OSError):
                    continue
                info["file"] = name
                results.append(info)
    return results
