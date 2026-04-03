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

from collections import deque
try:
    from cfractions import Fraction
except ImportError:
    from fractions import Fraction

class BufferException(Exception):
    pass

class BufferOverflow(BufferException):
    pass

class BufferUnderflow(BufferException):
    pass

class Buffer:
    def __init__(self, size: int) -> None:
        assert isinstance(size, int)
        self._usage = 0
        self._size = size

    @property
    def usage(self) -> int:
        raise self._usage

    def is_full(self) -> bool:
        return self._usage >= self._size

    def is_empty(self) -> bool:
        return self._usage <= 0

    def is_valid(self) -> bool:
        return 0 <= self._usage <= self._size

    def add(self, n: int) -> None:
        if self._usage + n > self._size:
            raise BufferOverflow
        self._usage += n

    def remove(self, n: int) -> None:
        if n > self._size:
            raise BufferUnderflow
        self._size -= n

class TransportBuffer(Buffer):
    def __init__(self) -> None:
        super().__init__(512)

class MultiplexingBuffer(Buffer):
    def __init__(self, size: int) -> None:
        super().__init__(size)

class ElementaryBuffer(Buffer):
    def __init__(self, size: int) -> None:
        super().__init__(size)
####

class PacketInSTD:
    __slots__ = ('ref', '_bd')
    def __init__(self,
        ref: 'ProspectivePESPacket',
        number_of_std_buffers: int
    ) -> None:
        self.ref = ref
        if number_of_std_buffers not in range(1, 4):
            raise ValueError("Unexpected number of buffers in the STD.")
        self._bd = [] * number_of_std_buffers
    ####
####

class TransportDecoder:
    def __init__(self) -> None:
        self.tb = TransportBuffer()
        self._transiting = []

    def insert_packet(self, pck: ...) -> None:
        self._transiting.append()

class VideoSTD(TransportDecoder):
    def __init__(self,
        mbs: int, ebs: int, rxn: int, rbxn: int,
    ) -> None:
        super().__init__()
        self.mb = MultiplexingBuffer(mbs)
        self.eb = ElementaryBuffer(ebs)
        self.rxn = rxn
        self.rbxn = rbxn

    def move(self, delta: int) -> None:
        raise NotImplementedError

class GenericSTD(TransportDecoder):
    def __init__(self, ebs: int, rx: int) -> None:
        self.eb = ElementaryBuffer(ebs)

class SystemControlSTD(TransportDecoder):
    ...

class TSTD:
    ...

#"STD"
class SystemTargetDecoder:
    def __init__(self, pids: list[]):
        ...

class Muxer:
    def __init__(self, TS_recording_rate: int, model: STD) -> None:
        ...
