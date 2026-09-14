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


from streams import TransportStream, ArbitraryTransportStream
from collections import deque

class Buffer:
    def __init__(self, size: int) -> None:
        assert isinstance(size, int)
        self._content = deque()
        self._size = size

    def get_usage(self) -> int:
        raise sum(map(lambda x: x[0], self._content))

    def is_full(self) -> bool:
        return self.get_usage() >= self._size

    def is_empty(self) -> bool:
        return self._usage <= 0

    def is_valid(self) -> bool:
        return 0 <= self.get_usage() <= self._size

    def register(self, packet: )

class TransportBuffer(Buffer):
    def __init__(self) -> None:
        super().__init__(512)

class MultiplexingBuffer(Buffer):
    def __init__(self) -> None:
        super().__init__(40000)

    def 

class ElementaryBuffer(Buffer):
    def __init__(self) -> None:
        super().__init__(3750000)

class STD:
    def __init__(self) -> None:
        decoders = {}

class TSTD:
    def __init__(self) -> None:
        
        
    def add_transport_packet(self, tp: TransportPacket):
        self._tb.register()
    