#!/usr/bin/env python3
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

from dataclasses import dataclass
from pathlib import Path
from struct import unpack, pack

from enum import IntFlag, IntEnum, auto as eauto
from parsers.utils import ProspectivePESPacket, TSPair
from utils.hash import hash_asset

class PesIndexFileType:
    VIDEO = eauto()
    AUDIO = eauto()


class PacketAttributeFlags(IntFlag):
    DTS_present = eauto() # must be 0b01 to be aligned to H.222
    PTS_present = eauto() # must be 0b10 to be aligned to H.222
    TP_plan = eauto()

class VariableLength:
    @staticmethod
    def encode(length: int) -> bytes:
        bstr = bytearray()
        if length <= 0:
            raise ValueError("Length cannot be zero.")
        while length > 0:
            byte = length & 0x7F
            length = (length >> 7) - 1
            bstr.append(byte)
        bstr[-1] |= 0x80
        return bytes(bstr)

    #%%
    @staticmethod
    def decode(bstr: bytes) -> tuple[int, int]:
        length = 0
        shift = 0
        # don't endlessly parse incorrect bytestrings
        for ix, byte in enumerate(bstr[:8], 1):
            length += (byte & 0x7F) << shift
            if byte & 0x80:
                return length, ix
            shift += 7
            length += 1 << shift
        raise ValueError("bytestring is not valid.")

#%%
@dataclass
class PacketAttributeFields:
    def __init__(self, tspair: TSPair, pes_packet_meta: ProspectivePESPacket) -> None:
        self.tspair = tspair
        self.pes_packet_meta = pes_packet_meta

    def to_bytes(self) -> bytes:
        flags = self.tspair.get_pts_dts_flag()

        bstring = bytearray([0])

        bstring += VariableLength.encode(self.pes_packet_meta.header_size)
        bstring += VariableLength.encode(self.pes_packet_meta.payload_size)

        if flags & PacketAttributeFlags.PTS_present:
            bstring += pack(">Q", self.tspair.pts)[3:]
            if flags & PacketAttributeFlags.DTS_present:
                bstring += pack(">Q", self.tspair.dts)[3:]
        tp_plan = self.pes_packet_meta.get_tp_plan()
        if tp_plan is not None:
            flags |= PacketAttributeFlags.TP_plan
            bstring += VariableLength.encode(len(tp_plan)) + bytes(tp_plan)
        # PES packet metadata is always present
        bstring[0] = flags
        return VariableLength.encode(len(bstring)) + bstring

    @classmethod
    def from_bytes(cls, data: bytes) -> 'PacketAttributeFields':
        size, offset = VariableLength.decode(data)
        if len(data) < size + offset:
            raise BufferError("Not enough bytes in data.")
        flags = data[offset]
        offset += 1

        # PES header and data size always stored
        pes_header_size, n = VariableLength.decode(data[offset:])
        offset += n
        pes_payload_size, n = VariableLength.decode(data[offset:])
        offset += n

        hpp = ProspectivePESPacket(pes_header_size, pes_payload_size)

        if flags & PacketAttributeFlags.PTS_present:
            pts = unpack(">Q", b'\x00' * 3 + data[offset:offset+5])[0]
            flags &= ~PacketAttributeFlags.PTS_present
            offset += 5
            if flags & PacketAttributeFlags.DTS_present:
                dts = unpack(">Q", b'\x00' * 3 + data[offset:offset+5])[0]
                offset += 5
            else:
                dts = None
            flags &= ~(PacketAttributeFlags.PTS_present | PacketAttributeFlags.DTS_present)
            tsp = TSPair(pts, dts)
        else:
            raise RuntimeError("PES packets must have a PTS")

        if flags & PacketAttributeFlags.TP_plan:
            num_tp_packets, n = VariableLength.decode(data[offset:])
            offset += n
            hpp.set_tp_plan(list(data[offset:offset + num_tp_packets]))
        return tsp, hpp


class EsIndex:
    def __init__(self, stream_type: int, ) -> None:
        self.stream_type = stream_type
        self.prospective_packets = []

    def write_to_file(self, fp: Path | str) -> None:
        fp = Path(fp)
        assert fp.parent.exists()

    @classmethod
    def from_asset(cls, asset_file: Path | str) -> 'EsIndex':
        ...

    @classmethod
    def from_index_file(cls, index_file: Path | str) -> 'EsIndex':
        ...
