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

from enum import IntEnum
from bitstream import BitReader

class NALType(IntEnum):
    FILLER = 12
    EOSTR = 11
    EOSEQ = 10
    AUD = 9
    PPS = 8
    SPS = 7
    SEI = 6
    I_IDR=5
    Not_IDR=1
    unk = 0

    def _missing_(cls, v: ...) -> 'NALType':
        return cls(0)

class SEI(IntEnum):
    BufferingPeriod = 0
    PictureTiming = 1
    Filler = 3
    UserDataUnregistered = 5
    RecoveryPoint = 6
    DecRefPicMarking = 7

class PrimaryPicType(IntEnum):
    I = 0x00
    P = 0x01
    B = 0x02
    UNK = 0xFF

    def to_string(self) -> str:
        return self._name_

def parse_nal_unit_type(nal_first_byte: int) -> NALType:
    assert nal_first_byte >> 7 == 0, "forbidden_zero_bit not zero"
    return NALType(nal_first_byte & 0x1F)

def nal_requires_annexb_zero_byte(nal_unit_type: NALType) -> bool:
    return nal_unit_type in (NALType.AUD, NALType.SPS, NALType.PPS)

def parse_hrd_parameters(br: BitReader):
    cpb_cnt_minus1 = br.read_ue()
    bit_rate_scale = br.read_bits(4)  # bit_rate_scale
    cpb_size_scale = br.read_bits(4)  # cpb_size_scale

    cpb_params = []
    for _ in range(cpb_cnt_minus1 + 1):
        bit_rate_value_minus1 = br.read_ue()  # bit_rate_value_minus1
        cpb_size_value_minus1 = br.read_ue()  # cpb_size_value_minus1
        cbr_flag = br.read_bit() # cbr_flag
        cpb_params.append({'BitRate': (bit_rate_value_minus1+1) << (6+bit_rate_scale),
                           'CpbSize': (cpb_size_value_minus1+1) << (4+cpb_size_scale),
                           'cbr_flag': cbr_flag})

    return {
        "cpb_cnt_minus1": cpb_cnt_minus1,
        'CpbParams': cpb_params,
        "initial_cpb_removal_delay_length_minus1": br.read_bits(5),
        "cpb_removal_delay_length_minus1": br.read_bits(5),
        "dpb_output_delay_length_minus1": br.read_bits(5),
        "time_offset_length": br.read_bits(5),
    }

def parse_sps(rbsp: bytes) -> dict[str, int]:
    br = BitReader(rbsp)

    sps = {}
    profile_idc = sps['profile_idc'] = br.read_bits(8)
    sps['constraint_set_byte'] = br.read_bits(8) # 6 flags + 2 reserved
    sps['level_idc'] = br.read_bits(8)
    br.read_ue()         # seq_parameter_set_id

    if profile_idc in (100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134):
        chroma_format_idc = br.read_ue()
        if chroma_format_idc == 3:
            br.read_bit() # separate_colour_plane_flag
        br.read_ue()      # bit_depth_luma_minus8
        br.read_ue()      # bit_depth_chroma_minus8
        br.read_bit()     # qpprime_y_zero_transform_bypass_flag
        if br.read_bit(): # seq_scaling_matrix_present_flag
            for i in range(8 if chroma_format_idc != 3 else 12):
                if br.read_bit():
                    size = 16 if i < 6 else 64
                    last = 8
                    for _ in range(size):
                        last = (last + br.read_ue()) & 0xff

    br.read_ue()  # log2_max_frame_num_minus4
    match br.read_ue(): # picture_order_cnt_type
        case 0:
            br.read_ue()
        case 1:
            br.read_bit()
            br.read_ue()
            br.read_ue()
            for _ in range(br.read_ue()):
                br.read_ue()

    br.read_ue()  # max_num_ref_frames
    br.read_bit() # gaps_in_frame_num_value_allowed_flag

    sps['pic_width_in_mbs_minus1'] = br.read_ue()
    sps['pic_height_in_map_units_minus1'] = br.read_ue()

    sps['frame_mbs_only_flag'] = frame_mbs_only_flag = br.read_bit()
    if not frame_mbs_only_flag:
        sps['mb_adaptive_frame_field_flag'] = br.read_bit()

    br.read_bit()      # direct_8x8_inference_flag

    if br.read_bit():  # frame_cropping_flag
        br.read_ue()
        br.read_ue()
        br.read_ue()
        br.read_ue()

    # --- VUI ---
    vui = {}
    if br.read_bit():     # vui_parameters_present_flag
        if br.read_bit(): # aspect_ratio_info_present
            aspect_ratio_idc = br.read_bits(8)
            if aspect_ratio_idc == 255:
                br.read_bits(16)
                br.read_bits(16)
            vui['aspect_ratio_idc'] = aspect_ratio_idc

        if br.read_bit():  # overscan_info_present
            br.read_bit()

        if br.read_bit():   # video_signal_type_present
            br.read_bits(3) # video_format
            br.read_bit()   # video_full_range_flag

            if br.read_bit():
                vui['colour_primaries'] = br.read_bits(8)
                vui['transfer_characteristics'] = br.read_bits(8)
                vui['matrix_coefficients'] = br.read_bits(8)

        if br.read_bit():  # chroma_loc_info_present
            br.read_ue()
            br.read_ue()

        if br.read_bit():  # timing_info_present_flag
            vui['num_units_in_tick'] = br.read_bits(32)
            vui['time_scale'] = br.read_bits(32)
            vui['fixed_frame_rate_flag'] = br.read_bit()

        nal_hrd_present = br.read_bit()
        if nal_hrd_present:
            vui |= parse_hrd_parameters(br)

        vcl_hrd_present = br.read_bit()
        if vcl_hrd_present:
            if nal_hrd_present: raise NotImplementedError("VCL + NAL HRD not supported.")
            vui |= parse_hrd_parameters(br)

        if nal_hrd_present or vcl_hrd_present:
            vui['low_delay_hrd_flag'] = br.read_bit()

        vui['pic_struct_present_flag'] = br.read_bit()
    return sps | vui
####
