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

from abc import abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, Iterable

from mpeg_common import MPEGClock, TSPair

@dataclass
class AccessUnit:
    size: int = 0

#%%
class Parser:
    def __init__(self, fp: Path | str) -> None:
        if not (fp := Path(fp)).exists():
            raise OSError("Input file does not exist.")
        self._fp = fp

    def __iter__(self) -> AccessUnit:
        yield from self.parse()

    def parse_stream(self, *args, **kwargs) -> list[AccessUnit]:
        return [au for au in self.parse(*args, **kwargs)]
    
    @abstractmethod
    def parse(self, *args, **kwargs):
        raise NotImplementedError

@dataclass
class ProspectivePESPacket:
    header_size: int
    payload_size: int
    _packetization_plan: list[int] | None = None
    
    def set_transport_packetization_plan(self, plan: list[int]) -> None:
        """
        Let the user specify how each element within the access unit shall be
        packetized. I.e a section may be conveyed with transport_priority=1,
        requiring adaptation field stuffing for isolation.
        """
        if not sum(plan) == self.payload_size + self.header_size:
            raise ValueError("Packet plan cannot store PES payload.")
        if max(plan) > 184:
            raise ValueError("At least one packet does not fit in a Transport Packet.")
        self._packetization_plan = plan
    
    @property
    def size(self) -> int:
        return self.header_size + self.payload_size
    
    def get_tp_count(self) -> int:
        if self._packetization_plan is not None:
            return len(self._packetization_plan)
        return (self.size + 183) // 184
    
class Indexer:
    _parser: Parser | None = None
    def __init__(
        self,
        input_file: Path | str,
        index_file: Path | str,
     ) -> None:
        assert self.__class__._parser is not None
        input_file = Path(input_file)
        index_file = Path(index_file)
        if not input_file.parent.exists():
            raise OSError("Input file does not exist.")
        if not index_file.parent.exists():
            raise OSError("Target directory for the index file does not exist.")

        self.input_file = input_file
        self.index_file = index_file

    @classmethod
    def estimate_pes_packet_size(cls, au: AccessUnit, ts_pair: TSPair) -> int:
        """
        Helper to estimate the PES packet total size for the given access unit.
        """
        
        # packet_start_code_prefix + stream_id + PES_packet_length
        header_size = 6
        # Classical PES header
        header_size += 3

        # PTS should always be provided
        if ts_pair.pts is not None:
            header_size += 5
            if ts_pair.pts != ts_pair.dts:
                header_size += 5

        return ProspectivePESPacket(header_size, au.size)
        
    @classmethod
    def estimate_tp_count_for_pes_packet(cls, pes_packet_size: int) -> int:
        #188 - 4 for TS header overhead
        return (pes_packet_size + 183) // 184

    def get_pts_dts_of_access_unit(self,
           first_pts = MPEGClock.PTS,
    ) -> Generator[TSPair, AccessUnit, None]:
        """
        Generator of PTS DTS given the incoming access unit
        """
        au = yield
        pts = first_pts
        while au is not None:
            au = yield TSPair(pts, pts)
            pts += 1
    ####

    def index(self,
      pts_dts_generator: Generator[TSPair, AccessUnit, None] | None = None,
    ) -> None:
        """
        Index the input file given a pts_dts_generator of (pts, dts) pairs. If none is provided
        the indexer simply index based on the counter of access unit.
        """
        if pts_dts_generator is None:
            pts_dts_generator = self.get_pts_dts_of_access_unit()

        next(pts_dts_generator)
        for au in self.__class__._parser(self.input_file):
            pair = pts_dts_generator.send(au)
            pes_size = self.__class__.estimate_pes_packet_size(au, pair)
            tp_count = self.__class__.estimate_tp_count_for_pes_packet(pes_size)
        pts_dts_generator.close()
####
