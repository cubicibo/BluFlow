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

import struct
from fractions import Fraction
from consts import StreamType

descriptor_table = {
    'HEVC_video_descriptor': lambda x: HEVCDescriptor(x).video_descriptor_to_bytes(),
}

class _Descriptor:
    def __init__(self, parameters: dict[str, int]):
        self.parameters = parameters

    @staticmethod
    def _set_descriptor_length(b: bytearray) -> None:
        b[1] = len(b) - 2

    @abstractmethod
    def __bytes__(self) -> bytes:
        return self

class TSDecriptor(_Descriptor):
    @staticmethod
    def _convert_rate(rate: int | None, ceiling: bool = True) -> int:
        _mask: int = ((1 << 22) - 1)
        if isinstance(rate, int):
            rate_in_unit = (rate + 399*bool(ceiling)) // 400
            assert rate_in_unit <= _mask, "partial TS descriptor rate param overflow"
            return rate_in_unit & _mask
        return _mask

    def partial_transport_stream_descriptor_to_bytes(self) -> bytes:
        cls = __class__
        p = self.parameters
        data = bytearray([0x63, 0x00])

        peak_rate_in_units = cls._convert_rate(p['peak_rate'], ceiling=True)
        data += struct.pack(">I", peak_rate_in_units)[1:]

        min_overall_smoothing_rate = cls._convert_rate(p.get('minimum_overall_smoothing_rate', None), ceiling=False)
        data += struct.pack(">I", min_overall_smoothing_rate)[1:]

        maximum_overall_smoothing_buffer = p.get('maximum_overall_smoothing_buffer', 0x3FFF)
        assert maximum_overall_smoothing_buffer <= 0x3FFF, "maximum_overall_smoothing_buffer overflow"
        data += struct.pack(">H", maximum_overall_smoothing_buffer)

        cls._set_descriptor_length(data)
        return bytes(data)

class AC3Descriptor(_Descriptor):
    def registration_descriptor_to_bytes(self) -> bytes:
        ...
    def audio_descriptor_to_bytes(self) -> bytes:
        ...

class HDMVDescriptor(_Descriptor):
    def video_registration_descriptor_to_bytes(self) -> bytes:
        p = self.parameters
        data = bytearray([0x05 0x08, 0x48, 0x44, 0x4D, 0x56, 0xFF])

        data.append()

    def registration_descriptor_to_bytes(self) -> bytes:
        return bytes([0x05, 0x04, 0x48, 0x44, 0x4D, 0x56])

    def lpcm_audio_registration_descriptor_to_bytes(self) -> bytes:
        ...

    def copy_control_descriptor_to_bytes(self) -> bytes:
        # ffmpeg puts 0xfc??
        return bytes([0x88, 0x04, 0x0F, 0xFF, 0xFC, 0xFC])

class HEVCDescriptor(_Descriptor):
    def video_descriptor_to_bytes(self) -> bytes:
        p = self.parameters

        data = bytearray([0, 0])
        data.append(((p.get('profile_space') & 0b11) << 6) |
                    ((p.get('tier_flag') & 0b1) << 5) |
                    ((p.get('profile_idc') & 0x1F)))

        data += struct.pack(">I", p.get('profile_compatibility_indication'))
        data.append(((p.get('progressive_source_flag') & 1) << 7) |
                    ((p.get('interlaced_source_flag')  & 1) << 6) |
                    ((p.get('non_packed_constraint_flag') & 1) << 5) |
                    ((p.get('frame_only_constraint_flag') & 1) << 4))
        data += struct.pack(">I", p.get('copied_44bits'))
        data.append(p.get('level_idc'))
        data.append(((p.get('temporal_layer_subset_flag') & 1)     << 7) |
                    ((p.get('HEVC_still_present_flag') & 1)        << 6) |
                    ((p.get('HEVC_24hr_picture_present_flag') & 1) << 5) |
                    ((p.get('sub_pic_hrd_params_not_present_flag') & 1) << 4) |
                    ((p.get('HDR_WCG_idc') & 0b11)))

        if p.get('temporal_layer_subset_flag', 0):
            temporal_min = p.get('temporal_id_min') & 0x7
            temporal_max = p.get('temporal_id_max') & 0x7
            data += bytes([temporal_min << 5, temporal_max << 5])

        __class__._set_descriptor_length(data)
        return bytes(data)

class AVCDescriptor(_Descriptor):
    def timing_hrd_descriptor_to_bytes(self) -> bytes:
        p = self.parameters
        # Notation (value, bitfield length)
        # descriptor_tag    (8)
        # descriptor_length (8)
        # hrd_management_valid_flag       (1)
        # reserved                        (6)
        # picture_and_timing_info_present (1) (assumed always True)
        #   90kHz_flag                    (1) + 7 reserved
        #     N (32), K (32)
        #   num_units_in_tick (32)
        # flags (8)
        data = bytearray([42, 0])
        flags = p.get('hrd_management_valid_flag', 0) << 7
        flags|= p.get('picture_and_timing_info_present', 1)
        data.append(flags)

        uses_90khz_tb = p.get('90kHz_flag', 0)
        data.append(uses_90khz_tb << 7)
        if not uses_90khz_tb:
            NoK = Fraction(p.get('time_scale'), p.get('system_clock_frequency', 27000000))
            data += struct.pack(">I", NoK.numerator)
            data += struct.pack(">I", NoK.denominator)
        data += struct.pack(">I", p.get('num_units_in_tick'))

        flags = p.get('fixed_frame_rate_flag', 1) << 7
        flags|= p.get("temporal_poc_flag", 0) << 6
        flags|= p.get("picture_to_display_conversion_flag", 0) << 5

        data.append(flags)
        __class__._set_descriptor_length(data)
        return bytes(data)

    def video_descriptor_to_bytes(self) -> bytes:
        p = self.parameters
        data = bytearray([40, 4, 0, 0, 0, 0])

        data[5] |= p.get('Frame_Packing_SEI_not_present_flag', 1) << 5
        data[5] |= p.get('AVC_24_hour_picture_flag', 0) << 6
        data[5] |= p.get('AVC_still_present', 0) << 7

        data[4] = p['level_idc'] # must be specified
        data[3] = p.get('constraint_set_byte', 0)
        data[2] = p['profile_idc']

        __class__._set_descriptor_length(data)
        return bytes(data)
