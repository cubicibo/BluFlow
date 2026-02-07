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
from itertools import cycle
from pathlib import Path
from typing import Generator, Iterable

from mpeg_common import MPEGClock

@dataclass
class AccessUnit:
    size: int = 0

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
    def __init__(
        self,
        input_file: Path | str,
        index_file: Path | str,
     ) -> None:
        input_file = Path(input_file)
        index_file = Path(index_file)
        if not input_file.parent.exists():
            raise OSError("Input file does not exist.")
        if not index_file.parent.exists():
            raise OSError("Target directory for the index file does not exist.")

        self.input_file = input_file
        self.index_file = index_file

    @classmethod
    def estimate_pes_packet_size(cls, au: AccessUnit, pts: int, dts: int) -> int:
        """
        Helper to estimate the PES packet total size for the given access unit.
        """
        pes_packet_size = au.size
        # packet_start_code_prefix + stream_id + PES_packet_length
        pes_packet_size += 6
        # Classical PES header
        pes_packet_size += 3
        
        # PTS should always be provided
        if pts is not None:
            pes_packet_size += 5
            if pts != dts:
                pes_packet_size += 5
        return pes_packet_size
        
    def estimate_tp_count_for_pes_packet(cls, pes_packet_size: int) -> int:
        #188 - 4 for TS header overhead
        return (pes_packet_size + 183) // 184

    def get_pts_dts_of_access_unit(self,
           pts_delta: Generator[int, None, None] | Iterable[int] | int = 1,
           first_pts = MPEGClock.PTS,
    ) -> Generator[tuple[int, int], AccessUnit, None]:
        """
        Generator of 
        """
        if isinstance(pts_delta, int):
            if pts_delta < 0:
                raise ValueError("pts_delta must be monotonic.")
            pts_delta = cycle([pts_delta])

        au = yield
        pts = first_pts
        while au is not None:
            au = yield (pts, pts)
            pts += next(pts_delta)
    ####

    def index(self,
      pts_dts_generator: Generator[tuple[int, int], AccessUnit, None] | None = None,
    ) -> None:
        """
        Index the input file given a pts_dts_generator of (pts, dts) pairs. If none is provided
        the indexer simply index based on the counter of access unit.
        """
        if pts_dts_generator is None:
            pts_dts_generator = self.get_pts_dts_of_access_unit()

        next(pts_dts_generator)
        for au in Parser(self.index_file):
            pts, dts = pts_dts_generator.send(au)
            self.__class__.estimate_pes_packet_size(au, pts, dts)
