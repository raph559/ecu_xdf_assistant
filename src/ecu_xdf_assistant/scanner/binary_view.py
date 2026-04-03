from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass(slots=True)
class BinaryImage:
    path: Path
    data: bytes

    @classmethod
    def from_file(cls, path: str | Path) -> "BinaryImage":
        p = Path(path)
        return cls(path=p, data=p.read_bytes())

    @property
    def size(self) -> int:
        return len(self.data)

    def contains_range(self, offset: int, size: int) -> bool:
        return 0 <= offset and 0 <= size and (offset + size) <= self.size

    def read_int(self, offset: int, size_bytes: int, endian: str = "little", signed: bool = False) -> int:
        if not self.contains_range(offset, size_bytes):
            raise IndexError(f"offset out of range: 0x{offset:X}")
        return int.from_bytes(self.data[offset:offset + size_bytes], byteorder=endian, signed=signed)

    def read_series(
        self,
        offset: int,
        count: int,
        size_bytes: int,
        endian: str = "little",
        signed: bool = False,
    ) -> List[int]:
        total_size = count * size_bytes
        if not self.contains_range(offset, total_size):
            raise IndexError(f"range out of range: 0x{offset:X}+{total_size}")
        out: List[int] = []
        cursor = offset
        for _ in range(count):
            out.append(self.read_int(cursor, size_bytes=size_bytes, endian=endian, signed=signed))
            cursor += size_bytes
        return out

    def read_matrix(
        self,
        offset: int,
        rows: int,
        cols: int,
        size_bytes: int,
        endian: str = "little",
        signed: bool = False,
    ) -> List[List[int]]:
        total_size = rows * cols * size_bytes
        if not self.contains_range(offset, total_size):
            raise IndexError(f"matrix out of range: 0x{offset:X}+{total_size}")
        matrix: List[List[int]] = []
        cursor = offset
        for _ in range(rows):
            row = []
            for _ in range(cols):
                row.append(self.read_int(cursor, size_bytes=size_bytes, endian=endian, signed=signed))
                cursor += size_bytes
            matrix.append(row)
        return matrix
