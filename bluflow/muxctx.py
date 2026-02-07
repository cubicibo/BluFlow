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

from pathlib import Path
from typing import Optional, ContextManager, Generator
from contextlib import nullcontext
from dataclasses import dataclass
import struct

from consts import AdaptationFieldControl
from streams import TransportStream, TSPacket
from pespacket import PESPacket

@dataclass
class PacketAttribute:
    tp_count: int
    pck_size: int
    pts: int
    dts: Optional[int] = None

    @classmethod
    def from_pa(cls, bstr: bytes) -> 'PacketAttribute':
        assert bstr[0] == 80 and len(bstr) >= 15
        tp_cnt, pck_size = struct.unpack(">HI", bstr[1:7])
        dts, pts = cls._decode_timestamps(bstr[6:15])
        return cls(tp_cnt, pck_size >> 8, pts, dts)

    @staticmethod
    def _decode_timestamps(tc_string) -> tuple[int, int]:
        dts = (struct.unpack(">I", tc_string[:4])[0]) << 1
        dts += (tc_string[4] >> 7)

        # PTS has 39 bits, whom 6 are unused, so we assume 33 bits.
        pts = (tc_string[4] & 0x7F) << 32
        pts += struct.unpack(">I", tc_string[5:])[0]
        return dts, (pts >> 6)
####

#%%
class PAF:
    def __init__(self, fp: Path) -> None:
        self._fp = Path(fp)
        assert self._fp.exists()
        self._pid = None

    @property
    def pid(self) -> int:
        return self._pid

    def gen_packet_attribute(self) -> Generator[PacketAttribute, None, None]:
        """
        Yields packet attributes from the PA collection in the file.
        """
        with open(self._fp, 'rb') as f:
            buffer = f.read(0x7FFF)

            self._pid, header = __class__._read_header(buffer)
            assert 0 < self._pid < 0x1FFF, "Bad file header."
            buffer = buffer[2+1+len(header):]

            while buffer:
                yield PacketAttribute.from_pa(buffer[:15])
                buffer = buffer[15:]
                if len(buffer) < 15:
                    buffer += f.read(0x7FFF)
                    assert len(buffer) >= 15 or len(buffer) == 0
        ####

    @staticmethod
    def _read_header(buffer: bytes) -> tuple[int, bytes]:
        assert len(buffer) > 2 and len(buffer) > buffer[2]
        pid = struct.unpack(">H", buffer[:2])[0]
        header = buffer[3:3+buffer[2]]
        return pid, header


    def __iter__(self):
        self._gp = self.gen_packets()
        return self

    def __next__(self):
        return next(self._gp)
####

#%%%
class Demux:
    def __init__(self, ts: TransportStream, excluded_pids: Optional[list[int]] = None) -> None:
        self.ts = ts

        # PMT, SIT, PMP, PCR
        self.system_pids = [0x0000, 0x001F, 0x0100]
        self.excluded_pids = self.system_pids.copy() + [0x1001, 0x1FFF] #PCR, null packet
        if excluded_pids:
            self.excluded_pids += excluded_pids

    def index_streams(self, folder, pbar: ContextManager = nullcontext()) -> None:
        pafg = PAFGenerator(folder)

        pck_buffer = dict()

        if getattr(pbar, 'update', None) is None:
            pbar.update = lambda *args, **kwargs: None
        with pbar:
            for tp in self.ts:
                if tp.PID in self.excluded_pids:
                    continue
                assert tp.adaptation_field_control & AdaptationFieldControl.PAYLOAD
                pesp, cnt = __class__._proc_transport_packet(tp, pck_buffer)

                if cnt > 0:
                    pafg.add_packet(tp.PID, pesp, cnt)
                pbar.update()
        for pid, lpck in pck_buffer.items():
            pesp = PESPacket(b''.join(map(lambda pib: pib.payload, lpck)))
            pafg.add_packet(pid, pesp, len(lpck))
    ####

    def get_psi(self, psi_pids: Optional[list[int]] = None) -> dict[int, list[TSPacket]]:
        if psi_pids is not None:
            selected_pids = psi_pids
        else:
            selected_pids = self.system_pids
        sys_pkt = {pid: [] for pid in selected_pids}
        pid_done = set()
        for tp in filter(lambda tp: tp.PID in selected_pids, self.ts):
            # we don't parse the PCR which is the only packet that only contains adaptation
            assert tp.adaptation_field_control & AdaptationFieldControl.PAYLOAD
            match tp.PID:
                case 0x0000:
                    if 0 == len(sys_pkt[tp.PID]):
                        assert tp.payload_unit_start_indicator
                        sys_pkt[tp.PID].append(tp)
                        pid_done.add(tp.PID)
                case _:
                    if 0 == len(sys_pkt.get(tp.PID, None)) or not tp.payload_unit_start_indicator:
                        sys_pkt[tp.PID].append(tp)
                    else:
                        pid_done.add(tp.PID)
            if pid_done.issuperset(selected_pids):
                break
        return sys_pkt

    @staticmethod
    def _proc_transport_packet(tp: TSPacket, buffer: dict[int, list[TSPacket]]) -> Optional[tuple[PESPacket, int]]:
        ret = None, 0
        if tp.payload_unit_start_indicator and len(buffer.get(tp.PID, [])) > 0:
            tp_grp = buffer.pop(tp.PID)
            pesp = PESPacket(b''.join(map(lambda pib: pib.payload, tp_grp)))
            ret = (pesp, len(tp_grp))
        if buffer.get(tp.PID, None) is None:
            buffer[tp.PID] = []
        buffer[tp.PID].append(tp)
        return ret
####

#%%
class PAFGenerator:
    #Packet Attributes File Generator
    def __init__(self, folder: [Path | str]) -> None:
        self._folder = Path(folder)
        assert self._folder.exists()
        self._pids = dict()

    def add_packet(self, pid: int, packet: PESPacket, cnt: int) -> None:
        assert 0 <= pid <= 0x1FFF

        if pid not in self._pids:
            sequence = bytes([pid >> 8, pid & 0xFF])
            self._pids[pid] = self._folder.joinpath(f"{pid:04X}" + '.paf')
            with open(self._pids[pid], 'wb') as f:
                f.write(sequence + b'\x00')

        self.append_index_file(pid, packet, cnt)

    def append_index_file(self, pid: int, packet: PESPacket, cnt: int) -> None:
        assert packet.pts is not None

        if packet.dts is None:
            dts = packet.pts
        else:
            dts = packet.dts
        temporal = __class__.encode_pts_dts(packet.pts, dts)
        assert any(temporal), "Zero PTS and DTS is illegal."

        with open(self._pids[pid], 'ab') as f:
            spatial = struct.pack(">H", cnt) + struct.pack(">I", len(packet))[1:]
            f.write((b'P' + spatial + temporal))

    @staticmethod
    def encode_pts_dts(pts: int, dts: int) -> bytes:
        payload = bytearray(b'\x00'*9)
        # encode DTS MSBs.LSB
        payload[:4] = struct.pack(">I", (dts >> 1) & ((1 << 32) - 1))

        # encode PTS as 40 bits, easier than the misaligned 33 bits.
        payload[4:9] = struct.pack(">Q", (pts << 6) & ((1 << 39) - 1))[3:]
        payload[4] |= ((dts & 0x1) << 7)
        return payload

    def get_pafs(self):
        return self._pids
####
#%%

    

class Decoder:
    _VPID = None
    def __init__(self):
        self._tb = TransportBuffer()

    @classmethod
    def suitable_for(cls, pid: int) -> bool:
        assert cls._VPID is not None
        if isinstance(cls._VPID, int):
            return pid == cls._VPID
        return pid in cls._VPID

class VideoDecoder(Decoder):
    _VPID = 0x1011
    def __init__(self):
        super().__init__()
        self._mb = Buffer(40000)
        self._eb = Buffer(3750000)

class GraphicsDecoder(Decoder):
    _VPID = list(range(0x1200, 0x1220)) + list(range(0x1400, 0x1420))
    def __init__(self):
        super().__init__()
        self._tb = TransportBuffer()
        self._eb = Buffer(1 << 20)

class AudioDecoder(Decoder):
    _VPID = range(0x1100, 0x1120)
    def __init__(self, stream_type: int):
        super().__init__()
        dc = {
            'LPCM96': (536832, 20e6), #0x80
            'LPCM192':(1073664,30e6), #0x80 too
            'AC3CORE':(18640,  2e6), #0x81
            'DDPLUS': (137936, 48e6),# 0x84
            'MLP':    (524250, 48e6),# 0x83
            'DTS':    (43972,  5e6), #0x82
            'DTSHD':  (713563, 48e6),# 0x85, 0x86
            'DEXPR':  (7456,   2e6), #0xA1
            #DTS-HD LBR unused/unsupported
        }
        self._eb = Buffer(self._eb[stream_type])

class SystemDecoder(Decoder):
    _VPID = [0x0000, 0x0100, 0x01FF, 0x1001] # include PCR
    def __init__(self, stream_type: int):
        super().__init__()
        self._eb = Buffer(...) #1e6

SupportedDecoders = [SystemDecoder, VideoDecoder, AudioDecoder, GraphicsDecoder]


def remux(ts: TransportStream, std_model):
    dmx = Demux(ts)
    psi_packets = dmx.get_psi()
    dmx.index_streams(ts.path.parent)

    pafs = {pid: PAF(paf) for pid, paf in dmx.get_pafs().items()}
    decs = dict()
    for pid in pafs:
        decoder = next(filter(lambda d: d.suitable_for(pid), SupportedDecoders), None)
        assert decoder is not None
        decs[pid] = decoder(paf.stream_type)


#%%
# class Mux:
#     def __init__(self, index_folder: Path, input_ts: Path) -> None:
#         self._index_fp = Path(index_folder)
#         assert self._if.exists()

#         self._input_ts = Path(input_ts)
#         assert self._input_ts.exists()
