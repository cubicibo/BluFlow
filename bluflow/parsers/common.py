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
from typing import Generator, Any

from utils import MPEGClock, TSPair, AccessUnit, ProspectivePESPacket

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
    def estimate_pes_packet(cls, au: AccessUnit, ts_pair: TSPair) -> int:
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
    def retrieve_access_unit(cls, packet: Any) -> AccessUnit:
        if isinstance(packet, AccessUnit):
            return packet
        return next(filter(lambda e: isinstance(e, AccessUnit), packet))
    
    @classmethod
    def estimate_tp_count_for_pes_packet(cls, pes_packet: ProspectivePESPacket) -> int:
        #188 - 4 for TS header overhead
        return (pes_packet.size + 183) // 184

    @staticmethod
    def get_pts_dts_of_access_unit(
           first_pts = MPEGClock.PTS,
    ) -> Generator[TSPair, AccessUnit, None]:
        """
        Basic indexer
        """
        au = yield
        pts = first_pts
        while au is not None:
            au = yield TSPair(pts, pts)
            pts += 1
    ####

    def index(self, first_pts: int = MPEGClock.PTS) -> None:
        """
        Index the input file given the class pts_dts generator.
        """
        pts_dts_generator = self.__class__.get_pts_dts_of_access_unit(first_pts)
        lsr = []
        next(pts_dts_generator)
        for packet in self.__class__._parser(self.input_file):
            pair = pts_dts_generator.send(packet)
            au = self.__class__.retrieve_access_unit(packet)
            likely_pes = self.__class__.estimate_pes_packet(au, pair)
            tp_count = self.__class__.estimate_tp_count_for_pes_packet(likely_pes)
            lsr.append((pair, likely_pes, tp_count))
        pts_dts_generator.close()
        return lsr
####