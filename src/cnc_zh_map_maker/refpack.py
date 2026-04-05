"""EA RefPack (QFS) compression/decompression.

RefPack is EA's proprietary compression used in SAGE engine files.
Compressed files start with magic bytes: 0x00 0xFB (or EAR\0 header wrapper).
"""

from __future__ import annotations

import struct
from io import BytesIO


def is_refpack_compressed(data: bytes) -> bool:
    """Check if data is RefPack compressed (EAR\\0 header or raw 00 FB)."""
    if len(data) < 2:
        return False
    # EAR\0 wrapper
    if data[:4] == b"EAR\x00":
        return True
    # Raw RefPack magic
    if data[0] == 0x00 and data[1] == 0xFB:
        return True
    return False


def decompress(data: bytes) -> bytes:
    """Decompress RefPack/QFS compressed data.

    Handles both raw RefPack streams (00 FB header) and EAR\\0 wrapped data.
    """
    stream = BytesIO(data)

    # Check for EAR\0 wrapper
    magic = stream.read(4)
    if magic == b"EAR\x00":
        # EAR header: 4 bytes magic, then variable header, then RefPack stream
        # Read the rest as refpack data - the header contains compressed/decompressed sizes
        header_rest = stream.read(4)
        flags = header_rest[0]
        # The actual refpack stream follows
        refpack_data = stream.read()
        return _decompress_refpack(refpack_data)
    else:
        stream.seek(0)
        return _decompress_refpack(data)


def _decompress_refpack(data: bytes) -> bytes:
    """Decompress a raw RefPack stream (starts with 00 FB or 10 FB)."""
    stream = BytesIO(data)

    # Read header
    flags = stream.read(1)[0]
    magic = stream.read(1)[0]
    if magic != 0xFB:
        raise ValueError(f"Not a RefPack stream: expected 0xFB, got 0x{magic:02X}")

    # Determine decompressed size (3 or 4 bytes depending on flags)
    if flags & 0x80:
        # 4-byte decompressed size (big endian)
        size_bytes = stream.read(4)
        decompressed_size = struct.unpack(">I", size_bytes)[0]
    else:
        # 3-byte decompressed size (big endian)
        size_bytes = stream.read(3)
        decompressed_size = (size_bytes[0] << 16) | (size_bytes[1] << 8) | size_bytes[2]

    output = bytearray()

    while stream.tell() < len(data):
        # Read control byte
        b0 = stream.read(1)
        if not b0:
            break
        b0 = b0[0]

        if b0 < 0x80:
            # 2-byte command: copy 0-3 literal bytes, then copy from history
            b1 = stream.read(1)[0]
            num_literal = b0 & 0x03
            num_copy = ((b0 & 0x1C) >> 2) + 3
            copy_offset = ((b0 & 0x60) << 3) + b1 + 1
            output.extend(stream.read(num_literal))
            _copy_from_history(output, copy_offset, num_copy)

        elif b0 < 0xC0:
            # 3-byte command
            b1 = stream.read(1)[0]
            b2 = stream.read(1)[0]
            num_literal = ((b1 & 0xC0) >> 6) & 0x03
            num_copy = (b0 & 0x3F) + 4
            copy_offset = ((b1 & 0x3F) << 8) + b2 + 1
            output.extend(stream.read(num_literal))
            _copy_from_history(output, copy_offset, num_copy)

        elif b0 < 0xE0:
            # 4-byte command
            b1 = stream.read(1)[0]
            b2 = stream.read(1)[0]
            b3 = stream.read(1)[0]
            num_literal = b0 & 0x03
            num_copy = ((b0 & 0x0C) << 6) + b3 + 5
            copy_offset = ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1
            output.extend(stream.read(num_literal))
            _copy_from_history(output, copy_offset, num_copy)

        elif b0 < 0xFC:
            # Literal-only command
            num_literal = ((b0 & 0x1F) << 2) + 4
            output.extend(stream.read(num_literal))

        else:
            # End-of-stream or final literals
            num_literal = b0 & 0x03
            if num_literal > 0:
                output.extend(stream.read(num_literal))
            break

    return bytes(output[:decompressed_size])


def _copy_from_history(output: bytearray, offset: int, count: int) -> None:
    """Copy bytes from output history (handles overlapping copies)."""
    start = len(output) - offset
    for i in range(count):
        output.append(output[start + i])


def compress(data: bytes) -> bytes:
    """Compress data using RefPack algorithm.

    Returns raw RefPack stream (no EAR wrapper).

    RefPack encoding rules:
    - 0x00-0x7F: 2-byte copy command (can carry 0-3 preceding literals)
    - 0x80-0xBF: 3-byte copy command (can carry 0-3 preceding literals)
    - 0xC0-0xDF: 4-byte copy command (can carry 0-3 preceding literals)
    - 0xE0-0xFB: Plain literal command (4-112 bytes, multiples of 4)
    - 0xFC-0xFF: End of stream (0-3 trailing literals)
    """
    output = bytearray()

    # Header: flags=0x10, magic=0xFB, 3-byte decompressed size (big endian)
    output.append(0x10)
    output.append(0xFB)
    size = len(data)
    output.append((size >> 16) & 0xFF)
    output.append((size >> 8) & 0xFF)
    output.append(size & 0xFF)

    # Build list of (literal_bytes, copy_offset, copy_length) tuples
    # Then encode them with literal counts embedded in copy commands
    commands: list[tuple[bytes, int, int]] = []  # (literals, offset, length)
    pos = 0
    pending_literals = bytearray()

    while pos < size:
        best_offset = 0
        best_length = 0

        # Search for matches in a limited window
        max_search = min(pos, 0x20000)
        for search_pos in range(max(0, pos - max_search), pos):
            length = 0
            max_len = min(size - pos, 1028)
            while length < max_len and data[search_pos + length] == data[pos + length]:
                length += 1
            if length > best_length:
                best_length = length
                best_offset = pos - search_pos

        # Validate match fits an encoding:
        # 2-byte: length 3-10, offset 1-1024
        # 3-byte: length 4-67, offset 1-16384
        # 4-byte: length 5-1028, offset 1-131072
        usable = (best_length >= 3 and best_offset <= 1024 and best_length <= 10) or \
                 (best_length >= 4 and best_offset <= 16384 and best_length <= 67) or \
                 (best_length >= 5 and best_offset <= 131072)

        if usable:
            commands.append((bytes(pending_literals), best_offset, best_length))
            pending_literals = bytearray()
            pos += best_length
        else:
            pending_literals.append(data[pos])
            pos += 1

    # Remaining literals (no following copy)
    trailing_literals = bytes(pending_literals)

    # Encode commands
    for literals, copy_offset, copy_length in commands:
        # Emit large literal blocks (multiples of 4, up to 112)
        # Keep at most 3 trailing literals for the copy command
        lit_pos = 0
        total_lits = len(literals)

        # Calculate how many to emit as standalone literal commands
        # We want (total_lits - lit_to_keep) to be a multiple of 4
        lit_to_keep = total_lits % 4  # 0-3 literals to embed in copy command
        lit_to_emit = total_lits - lit_to_keep

        while lit_pos < lit_to_emit:
            chunk = min(lit_to_emit - lit_pos, 112)
            aligned = (chunk // 4) * 4
            if aligned < 4:
                break
            b0 = 0xE0 | (((aligned - 4) >> 2) & 0x1F)
            output.append(b0)
            output.extend(literals[lit_pos:lit_pos + aligned])
            lit_pos += aligned

        # Remaining 0-3 literals get embedded in the copy command
        num_literal = total_lits - lit_pos
        literal_chunk = literals[lit_pos:lit_pos + num_literal]

        offset = copy_offset - 1

        if copy_length <= 10 and offset < 0x400:
            # 2-byte command: [b0 b1] [literals] — length 3-10, offset 0-1023
            b0 = ((offset >> 3) & 0x60) | ((copy_length - 3) << 2) | num_literal
            b1 = offset & 0xFF
            output.append(b0)
            output.append(b1)
            output.extend(literal_chunk)
        elif copy_length >= 4 and copy_length <= 67 and offset < 0x4000:
            # 3-byte command: [b0 b1 b2] [literals] — length 4-67, offset 0-16383
            b0 = 0x80 | (copy_length - 4)
            b1 = (num_literal << 6) | ((offset >> 8) & 0x3F)
            b2 = offset & 0xFF
            output.append(b0)
            output.append(b1)
            output.append(b2)
            output.extend(literal_chunk)
        else:
            # 4-byte command: [b0 b1 b2 b3] [literals]
            b0 = 0xC0 | ((offset >> 12) & 0x10) | (((copy_length - 5) >> 6) & 0x0C) | num_literal
            b1 = (offset >> 8) & 0xFF
            b2 = offset & 0xFF
            b3 = (copy_length - 5) & 0xFF
            output.append(b0)
            output.append(b1)
            output.append(b2)
            output.append(b3)
            output.extend(literal_chunk)

    # Emit trailing literals (no copy command follows)
    lit_pos = 0
    while len(trailing_literals) - lit_pos >= 4:
        chunk = min(len(trailing_literals) - lit_pos, 112)
        aligned = (chunk // 4) * 4
        b0 = 0xE0 | (((aligned - 4) >> 2) & 0x1F)
        output.append(b0)
        output.extend(trailing_literals[lit_pos:lit_pos + aligned])
        lit_pos += aligned

    # End marker with 0-3 trailing literals
    remaining = len(trailing_literals) - lit_pos
    output.append(0xFC | remaining)
    output.extend(trailing_literals[lit_pos:])

    return bytes(output)
