#!/usr/bin/env python3
"""Extract RetroArch's compiled Git revision from Android APK ELF libraries."""

import argparse
import re
import struct
import zipfile
from pathlib import Path


SYMBOL_NAME = "retroarch_git_version"
REVISION_PATTERN = re.compile(rb"[0-9a-fA-F]{7,40}")


class ElfSymbolNotFound(ValueError):
    pass


def extract_revision_from_apk(apk_path, allow_missing=False):
    revisions = {}
    missing = []
    libraries = []
    with zipfile.ZipFile(apk_path) as archive:
        bad_entry = archive.testzip()
        if bad_entry:
            raise ValueError(f"APK archive integrity failure at {bad_entry}")
        for name in archive.namelist():
            if not re.fullmatch(r"lib/[^/]+/libretroarch-activity\.so", name):
                continue
            libraries.append(name)
            try:
                revision = extract_elf_symbol(archive.read(name), SYMBOL_NAME).decode("ascii")
            except ElfSymbolNotFound:
                missing.append(name)
                continue
            if not REVISION_PATTERN.fullmatch(revision.encode("ascii")):
                raise ValueError(f"Invalid RetroArch Git revision in {name}: {revision!r}")
            revisions[name] = revision.lower()

    if not libraries:
        raise ValueError("APK contains no libretroarch-activity.so")
    if missing:
        if revisions:
            raise ValueError(
                "APK native libraries have inconsistent Git revision availability: "
                f"present in {sorted(revisions)}, missing from {sorted(missing)}"
            )
        if allow_missing:
            return None
        raise ElfSymbolNotFound(
            "APK native libraries do not embed retroarch_git_version"
        )
    unique = set(revisions.values())
    if len(unique) != 1:
        raise ValueError(f"APK native libraries contain divergent revisions: {revisions}")
    return unique.pop()


def extract_elf_symbol(image, requested_name):
    if image[:4] != b"\x7fELF" or len(image) < 52:
        raise ValueError("Native library is not an ELF file")
    elf_class = image[4]
    data_encoding = image[5]
    if elf_class not in (1, 2) or data_encoding not in (1, 2):
        raise ValueError("Unsupported ELF class or byte order")
    endian = "<" if data_encoding == 1 else ">"

    if elf_class == 2:
        header = struct.unpack_from(endian + "HHIQQQIHHHHHH", image, 16)
        section_offset, section_size, section_count = header[5], header[10], header[11]
        section_format = endian + "IIQQQQIIQQ"
        symbol_format = endian + "IBBHQQ"
    else:
        header = struct.unpack_from(endian + "HHIIIIIHHHHHH", image, 16)
        section_offset, section_size, section_count = header[5], header[10], header[11]
        section_format = endian + "10I"
        symbol_format = endian + "IIIBBH"

    expected_section_size = struct.calcsize(section_format)
    if section_size < expected_section_size:
        raise ValueError("Invalid ELF section header size")
    sections = []
    for index in range(section_count):
        offset = section_offset + index * section_size
        if offset + expected_section_size > len(image):
            raise ValueError("ELF section headers are truncated")
        values = struct.unpack_from(section_format, image, offset)
        if elf_class == 2:
            name, kind, flags, address, file_offset, size, link, info, alignment, entry_size = values
        else:
            name, kind, flags, address, file_offset, size, link, info, alignment, entry_size = values
        sections.append(
            {
                "kind": kind,
                "address": address,
                "offset": file_offset,
                "size": size,
                "link": link,
                "entry_size": entry_size,
            }
        )

    for symbol_section in sections:
        if symbol_section["kind"] not in (2, 11) or not symbol_section["entry_size"]:
            continue
        if symbol_section["link"] >= len(sections):
            raise ValueError("ELF symbol string table link is invalid")
        string_section = sections[symbol_section["link"]]
        strings = _slice(image, string_section["offset"], string_section["size"], "ELF string table")
        symbol_data = _slice(
            image, symbol_section["offset"], symbol_section["size"], "ELF symbol table"
        )
        native_symbol_size = struct.calcsize(symbol_format)
        for offset in range(0, len(symbol_data), symbol_section["entry_size"]):
            if offset + native_symbol_size > len(symbol_data):
                break
            values = struct.unpack_from(symbol_format, symbol_data, offset)
            if elf_class == 2:
                name_offset, info, other, section_index, value, size = values
            else:
                name_offset, value, size, info, other, section_index = values
            name = _cstring(strings, name_offset)
            if name != requested_name:
                continue
            if section_index == 0 or section_index >= len(sections) or size <= 0:
                raise ValueError(f"ELF symbol {requested_name} has no readable definition")
            target = sections[section_index]
            relative = value - target["address"]
            if relative < 0 or relative + size > target["size"]:
                raise ValueError(f"ELF symbol {requested_name} lies outside its section")
            return _slice(
                image, target["offset"] + relative, size, f"ELF symbol {requested_name}"
            ).rstrip(b"\0")
    raise ElfSymbolNotFound(f"ELF symbol not found: {requested_name}")


def _slice(data, offset, size, label):
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError(f"{label} is truncated")
    return data[offset : offset + size]


def _cstring(data, offset):
    if offset < 0 or offset >= len(data):
        return ""
    end = data.find(b"\0", offset)
    if end == -1:
        return ""
    return data[offset:end].decode("ascii", errors="replace")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("apk", type=Path)
    args = parser.parse_args()
    print(extract_revision_from_apk(args.apk))


if __name__ == "__main__":
    main()
