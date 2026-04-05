"""Binary I/O utilities for SAGE .map file format.

The SAGE map format uses a chunk-based structure:
1. String dictionary (asset names mapped to indices)
2. Sequential asset chunks, each with: index(u32) + version(u16) + data_size(u32) + payload

Strings in the dictionary are stored as: length-prefixed (u16) ASCII strings,
each followed by a u32 index that references them.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from io import BytesIO
from typing import BinaryIO


@dataclass
class AssetName:
    """An entry in the asset name string dictionary."""
    name: str
    index: int


@dataclass
class AssetHeader:
    """Header for an asset chunk."""
    asset_index: int
    asset_name: str
    version: int
    data_size: int
    data_start: int  # offset where payload begins


class MapReader:
    """Reader for SAGE .map binary format."""

    def __init__(self, data: bytes):
        self.stream = BytesIO(data)
        self.asset_names: dict[int, str] = {}
        self._name_to_index: dict[str, int] = {}

    def read_u8(self) -> int:
        return struct.unpack("<B", self.stream.read(1))[0]

    def read_u16(self) -> int:
        return struct.unpack("<H", self.stream.read(2))[0]

    def read_u32(self) -> int:
        return struct.unpack("<I", self.stream.read(4))[0]

    def read_i32(self) -> int:
        return struct.unpack("<i", self.stream.read(4))[0]

    def read_f32(self) -> float:
        return struct.unpack("<f", self.stream.read(4))[0]

    def read_bytes(self, count: int) -> bytes:
        return self.stream.read(count)

    def read_ascii_string(self) -> str:
        length = self.read_u16()
        return self.stream.read(length).decode("ascii")

    def read_unicode_string(self) -> str:
        length = self.read_u16()
        return self.stream.read(length * 2).decode("utf-16-le")

    def tell(self) -> int:
        return self.stream.tell()

    def seek(self, pos: int) -> None:
        self.stream.seek(pos)

    def remaining(self) -> int:
        pos = self.stream.tell()
        self.stream.seek(0, 2)
        end = self.stream.tell()
        self.stream.seek(pos)
        return end - pos

    def read_string_dictionary(self) -> None:
        """Read the CkMp string dictionary at the start of the file.

        Format: "CkMp" magic, then repeated entries of:
          u32 index, u8 name_length, ASCII name_bytes
        Indices count down. The dictionary ends when data no longer matches
        this pattern (i.e., we've reached the first asset chunk).
        """
        magic = self.stream.read(4)
        if magic != b"CkMp":
            raise ValueError(f"Invalid map magic: {magic!r}, expected b'CkMp'")

        self.asset_names.clear()
        self._name_to_index.clear()

        while self.remaining() >= 5:  # At least u32 + u8
            pos = self.tell()
            index = self.read_u32()

            # Sanity check - indices should be reasonable (< 1000)
            if index > 1000:
                self.seek(pos)
                break

            name_len = self.read_u8()
            if name_len == 0 or name_len > 200:
                self.seek(pos)
                break

            if self.remaining() < name_len:
                self.seek(pos)
                break

            try:
                name = self.stream.read(name_len).decode("ascii")
            except UnicodeDecodeError:
                self.seek(pos)
                break

            # Validate it looks like a name (alphanumeric + underscore)
            if not all(c.isalnum() or c in "_" for c in name):
                self.seek(pos)
                break

            self.asset_names[index] = name
            self._name_to_index[name] = index

        # Index 1 is the root container asset in SAGE format.
        # It's not stored in the dictionary but is used as the first asset chunk index.
        if 1 not in self.asset_names:
            self.asset_names[1] = "_MapRoot"
            self._name_to_index["_MapRoot"] = 1

    def read_asset_header(self) -> AssetHeader | None:
        """Read the next asset chunk header."""
        if self.remaining() < 6:
            return None

        pos = self.tell()
        asset_index = self.read_u32()
        asset_name = self.asset_names.get(asset_index, f"Unknown_{asset_index}")

        version = self.read_u16()
        data_size = self.read_u32()
        data_start = self.tell()

        return AssetHeader(
            asset_index=asset_index,
            asset_name=asset_name,
            version=version,
            data_size=data_size,
            data_start=data_start,
        )

    def skip_asset(self, header: AssetHeader) -> None:
        """Skip past an asset's data payload."""
        self.seek(header.data_start + header.data_size)

    def read_asset_property(self) -> tuple[str, int, object]:
        """Read a single asset property (type, key, value)."""
        prop_type = self.read_u8()
        key_index = self.read_u16()
        key = self.asset_names.get(key_index, f"key_{key_index}")

        if prop_type == 0:  # Boolean
            value = self.read_u8() != 0
        elif prop_type == 1:  # UInt32
            value = self.read_u32()
        elif prop_type == 2:  # Int32
            value = self.read_i32()
        elif prop_type == 3:  # ASCII string
            value = self.read_ascii_string()
        elif prop_type == 4:  # Unicode string
            value = self.read_unicode_string()
        elif prop_type == 5:  # Float
            value = self.read_f32()
        else:
            raise ValueError(f"Unknown property type: {prop_type}")

        return key, prop_type, value


class MapWriter:
    """Writer for SAGE .map binary format."""

    def __init__(self):
        self.stream = BytesIO()
        self.asset_names: dict[str, int] = {}
        self._next_index = 1

    def register_asset_name(self, name: str) -> int:
        """Register an asset name and return its index."""
        if name not in self.asset_names:
            self.asset_names[name] = self._next_index
            self._next_index += 1
        return self.asset_names[name]

    def write_u8(self, value: int) -> None:
        self.stream.write(struct.pack("<B", value))

    def write_u16(self, value: int) -> None:
        self.stream.write(struct.pack("<H", value))

    def write_u32(self, value: int) -> None:
        self.stream.write(struct.pack("<I", value))

    def write_i32(self, value: int) -> None:
        self.stream.write(struct.pack("<i", value))

    def write_f32(self, value: float) -> None:
        self.stream.write(struct.pack("<f", value))

    def write_bytes(self, data: bytes) -> None:
        self.stream.write(data)

    def write_ascii_string(self, s: str) -> None:
        encoded = s.encode("ascii")
        self.write_u16(len(encoded))
        self.stream.write(encoded)

    def write_unicode_string(self, s: str) -> None:
        encoded = s.encode("utf-16-le")
        self.write_u16(len(s))
        self.stream.write(encoded)

    def write_string_dictionary(self) -> None:
        """Write the CkMp magic and string dictionary."""
        self.stream.write(b"CkMp")
        # Write entries sorted by index descending (as per format convention)
        entries = sorted(self.asset_names.items(), key=lambda x: x[1], reverse=True)
        for name, index in entries:
            self.write_u32(index)
            encoded = name.encode("ascii")
            self.write_u8(len(encoded))
            self.stream.write(encoded)

    def begin_asset(self, name: str, version: int) -> int:
        """Begin writing an asset chunk. Returns position of data_size field."""
        index = self.asset_names[name]
        self.write_u32(index)
        self.write_u16(version)
        size_pos = self.stream.tell()
        self.write_u32(0)  # Placeholder for data_size
        return size_pos

    def end_asset(self, size_pos: int) -> None:
        """Finish writing an asset chunk by filling in the data_size."""
        current_pos = self.stream.tell()
        data_size = current_pos - size_pos - 4  # Subtract the u32 size field itself
        self.stream.seek(size_pos)
        self.write_u32(data_size)
        self.stream.seek(current_pos)

    def write_property_bool(self, key: str, value: bool) -> None:
        self.write_u8(0)
        self.write_u16(self.asset_names[key])
        self.write_u8(1 if value else 0)

    def write_property_u32(self, key: str, value: int) -> None:
        self.write_u8(1)
        self.write_u16(self.asset_names[key])
        self.write_u32(value)

    def write_property_i32(self, key: str, value: int) -> None:
        self.write_u8(2)
        self.write_u16(self.asset_names[key])
        self.write_i32(value)

    def write_property_ascii(self, key: str, value: str) -> None:
        self.write_u8(3)
        self.write_u16(self.asset_names[key])
        self.write_ascii_string(value)

    def write_property_unicode(self, key: str, value: str) -> None:
        self.write_u8(4)
        self.write_u16(self.asset_names[key])
        self.write_unicode_string(value)

    def write_property_f32(self, key: str, value: float) -> None:
        self.write_u8(5)
        self.write_u16(self.asset_names[key])
        self.write_f32(value)

    def get_bytes(self) -> bytes:
        return self.stream.getvalue()

    def tell(self) -> int:
        return self.stream.tell()
