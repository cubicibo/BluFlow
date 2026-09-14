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

from enum import IntEnum, IntFlag

#US7844054B2
class COPY_PERMISSION(IntEnum):
    COPY_FREE = 0b00
    NO_MORE_COPY = 0b01
    COPY_ONCE = 0b10
    COPY_PROHIBITED = 0b11

class SCRAMBLING_CONTROL(IntEnum):
    NOT_SCRAMBLED = 0b00
    USER_DEFINED = 0b01
    USER_DEFINED_A = 0b10
    USER_DEFINED_B = 0b11

class AdaptationFieldControl(IntFlag):
    PAYLOAD = 0b01
    ADAPTATION = 0b10

class PTS_DTS_flags(IntFlag):
    DTS = 0b01
    PTS = 0b10

def __patch_enums():
    _ptsdts_new = PTS_DTS_flags.__new__
    def _new_ptsdts_flag(cls, value: int) -> PTS_DTS_flags:
        assert value & 0b11 != 0b01, "Illegal PTS_DTS_Flag"
        return _ptsdts_new(cls, value)
    PTS_DTS_flags.__new__ = _new_ptsdts_flag

    _afc_new = AdaptationFieldControl.__new__
    def _new_afc(cls, value: int) -> AdaptationFieldControl:
        assert value > 0, "Illegal adaptation_field_control"
        return _afc_new(cls, value)
    AdaptationFieldControl.__new__ = _new_afc
__patch_enums()


def __extend_enum(*inherited_enums):
    def wrapper(added_enum):
        joined = {}
        for inherited_enum in inherited_enums:
            for item in inherited_enum:
                joined[item.name] = item.value
            for item in added_enum:
                joined[item.name] = item.value
        return IntEnum(added_enum.__name__, joined)
    return wrapper

class VideoStreamType(IntEnum):
    MPEG1_VIDEO                 = 0x01
    MPEG2_VIDEO                 = 0x02
    AVC_VIDEO                   = 0x1B
    AVC_MVC_VIDEO               = 0x20
    HEVC_VIDEO                  = 0x24
    VVC_VIDEO                   = 0x33
    EVC_VIDEO                   = 0x35
    LCEVC_VIDEO                 = 0x36

class AudioStreamType(IntEnum):
    MPEG1_AUDIO                 = 0x03
    MPEG2_AUDIO                 = 0x04
    AAC_ADTS                    = 0x0F
    MPEG4_AAC_NO_LATM           = 0x1C

@__extend_enum(AudioStreamType, VideoStreamType)
class StreamType(IntEnum):
    PRIVATE_SECTIONS            = 0x05
    PRIVATE_PES_DATA            = 0x06
    DSM_CC                      = 0x08
    AUXILIARY                   = 0x0E
    MPEG4_SL_PACKETIZED         = 0x12
    MPEG4_SL_PES                = 0x13
    METADATA_PES                = 0x15
    MPEG4_TIMED_TEXT            = 0x1D
    HEVC_TEMPORAL_SUB_VIDEO     = 0x25
    VVC_TEMPORAL_SUB_VIDEO      = 0x34
####
