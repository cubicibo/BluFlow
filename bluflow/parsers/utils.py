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
from dataclasses import dataclass

class MPEGClock(IntEnum):
    PTS = 90000
    STC = 27000000

@dataclass
class AccessUnit:
    size: int = 0
    
@dataclass
class TSPair:
    pts: int
    dts: int | None = None
    def __post_init__(self) -> None:
        if self.dts is None:
            self.dts = self.pts
    
    def get_pts_dts_flag(self) -> int:
        return 0b11 if self.pts != self.dts else 0b10

@dataclass
class ProspectivePESPacket:
    header_size: int
    payload_size: int
    _packetization_plan: list[int] | None = None
    
    def set_tp_plan(self, plan: list[int]) -> None:
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
        
    def get_tp_plan(self) -> list[int] | None:
        return self._packetization_plan
    
    @property
    def size(self) -> int:
        return self.header_size + self.payload_size
    
    def get_tp_count(self) -> int:
        if self._packetization_plan is not None:
            return len(self._packetization_plan)
        return (self.size + 183) // 184