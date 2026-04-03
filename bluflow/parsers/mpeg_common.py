# -*- coding: utf-8 -*-
"""
Copyright (C) 2026 cibo
This file is part of BluFlow <https://github.com/cubicibo/BluFlow>.

BluFlow is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

BluFlow is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with BluFlow.  If not, see <http://www.gnu.org/licenses/>.
"""

from enum import IntEnum
from typing import BinaryIO, Generator, Callable

from bitstream import BitReader

class SEI(IntEnum):
    BufferingPeriod = 0
    PictureTiming = 1
    Filler = 3
    UserDataUnregistered = 5
    RecoveryPoint = 6
    DecRefPicMarking = 7
    ScalableNesting = 37

def yield_sei_units(rbsp: bytes) -> Generator[tuple[SEI | int, BitReader], None, None]:
    """
    This specific function was written by a LLM and is thereby under the MIT License.
    """
    br = BitReader(rbsp)

    while br.bitpos + 16 < len(rbsp) * 8:
        payload_type = 0
        while True:
            b = br.read_bits(8)
            payload_type += b
            if b != 0xFF:
                break

        payload_size = 0
        while True:
            b = br.read_bits(8)
            payload_size += b
            if b != 0xFF:
                break

        try:
            payload_type = SEI(payload_type)
        except ValueError:
            ...

        payload_start = br.bitpos
        payload_end = payload_start + payload_size * 8
        
        yield payload_type, br
        
        # don't use br as-is because it may not have done any parsing
        br.bitpos = payload_end
    return
####

def split_annexb_and_yield_nal(
        fp: BinaryIO,
        chunk_size: int = 4 << 20,
        f_requires_zero_byte: Callable[[bytes | bytearray], bool] = lambda *args, **kwargs : False
    ) -> Generator[bytes, None, None]:
    assert chunk_size >= 4096, "chunk_size shall at least be 4 KiB." 
    bytestream = bytearray(fp.read(chunk_size))
    start_pos = bytestream.find(b'\x00\x00\x01')
    if f_requires_zero_byte(bytestream[start_pos+3]):
        start_pos -= 1
        assert start_pos >= 0 and bytestream[start_pos] == 0, "Incorrect start code for NALU."

    while True:
        end_pos = bytestream.find(b'\x00\x00\x01', start_pos+3)
        
        # look ahead next NAL_unit_type to not steal its zero_byte
        if end_pos != -1:
            if f_requires_zero_byte(bytestream[end_pos+3]):
                end_pos -= 1
                assert bytestream[end_pos] == 0, "Incorrect start code for NALU."
            yield bytes(bytestream[start_pos:end_pos])
            bytestream = bytestream[end_pos:]
        else:
            new_data = fp.read(chunk_size)
            if len(new_data):
                bytestream += new_data
                continue
            yield bytes(bytestream[start_pos:])
            break
        start_pos = 0
    ####
####
