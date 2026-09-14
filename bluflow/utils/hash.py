#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copyright (C) 2026 cibo
This file is part of BluFlow <https://github.com/cubicibo/BluFlow>.

BluFlow is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

TSar is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with BluFlow.  If not, see <http://www.gnu.org/licenses/>.
"""

import os
from pathlib import Path
from typing import BinaryIO

def get_file_size(fs: BinaryIO) -> int:
    """
    Helper to get the position of 
    """
    saved_pos = fs.tell()
    fs.seek(0, os.SEEK_END)
    size = fs.tell()
    fs.seek(saved_pos, os.SEEK_SET)
    return size

def hash_asset(fp: Path | str, *, _chunk: int = 1 << 12) -> tuple[int, int]:
    """
    Perform coarse hashing of specified file, return file size and hash.
    """
    fp = Path(fp)
    assert fp.exists()
    
    if (kilo_chunk := _chunk >> 10) < 0 or kilo_chunk > 32:
        raise ValueError("_chunk shall reside within [1; 16]*1024 bytes.")
    
    data = bytearray()
    with open(fp, 'rb') as fs:
        fsize = get_file_size(fs)

        if fsize <= 3*_chunk:
            data += fs.read(fsize)
        else:
            data += fs.read(_chunk)
            fs.seek((fsize - _chunk) >> 1, os.SEEK_SET)
            data += fs.read(_chunk)
            fs.seek(-_chunk, os.SEEK_END)
            data += fs.read(_chunk)
    # we don't need secure hashing, just something sufficiently unique
    return fsize, hash(bytes(data))