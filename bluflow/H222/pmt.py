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

from struct import pack
from dataclasses import dataclass

from descriptors import _Descriptor

@dataclass
class ESInfo:
    stream_type: int
    elementary_PID: int
    descriptors: list[_Descriptor]

    def __post_init__(self):
        if not (0 < self.elementary_PID < 0x1FFF):
            raise ValueError("Illegal PID value.")

    def __bytes__(self) -> bytes:
        header= bytes([self.stream_type, (self.elementary_PID >> 8) & 0x1F, self.elementary_PID & 0xFF])

        es_info = b''.join(map(bytes, self.descriptors))
        len_es_info = len(es_info)
        return header + bytes([(len_es_info >> 8) & 0b11, len_es_info & 0xFF]) + es_info

class program_association_section:
    def __init__(self, transport_stream_id: int, network_PID: int, program_numer: int, program_map_PID) -> None:
        ...

class TS_program_map_section:
    def __init__(self,
        program_number: int,
        PCR_PID: int = 0x1FFF,
        global_info: list = [],
        ES_info: dict[int, ESInfo] = {}
    ) -> None:
        self.program_number = program_number
        self.PCR_PID = PCR_PID


    def to_bytes(self, version_number: int = 0, applicable: bool = True) -> bytes:
        # table_id (8), section_syntax_indicator (1), reserved 0 (3), section_length (12)
        bytestring = bytearray(b'\x02\x80\x00')
        section_and_length_2bytes = 0

        section_length = 9 # up to, incl., program_info_length

        bytestring += pack(">H", self.program_number)
        bytestring.extend(((version_number & 0x1F) << 1) | (applicable & 0x1))

        bytestring += b'\x00'*2 + pack(">H", 0x1FFF & self.PCR_PID)
        bytestring += b'\x00'*2 #program_info_length
