#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copyright (C) 2026 cibo
This file is part of SUPer <https://github.com/cubicibo/pTSd>.

pTSd is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

SUPer is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with SUPer.  If not, see <http://www.gnu.org/licenses/>.
"""

from common import AccessUnit, Parser
from dataclasses import dataclass
from pathlib import Path
from struct import unpack

from typing import Generator

@dataclass
class PGAccessUnit(AccessUnit):
    segment_type: int | None = None

class PGSParser(Parser):
    def __init__(self, fp: Path | str) -> None:
        assert (fp := Path(fp)).exists()
        self._fp = fp

    def parse(self) -> Generator[AccessUnit, None, None]:
        with open(self._fp, 'rb') as f:
            buff = f.read(1 << 20)
            while len(buff):
                assert buff[:2] == b'PG', len(buff)
                assert len(buff) >= 13
                size = unpack(">H", buff[11:13])[0]
                
                # + length (2) + type (1)
                yield PGAccessUnit(size + 3, segment_type=buff[10])
                buff = buff[size+13:]
                if len(buff) < 66000:
                    buff += f.read(1 << 20)
        return
                
                