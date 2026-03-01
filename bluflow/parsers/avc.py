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

from dataclasses import field, dataclass
from enum import IntEnum
from fractions import Fraction
from pathlib import Path

from typing import Generator

from bitstream import BitReader, remove_emulation_prevention as remove_emulation_prevention
from common import Parser, AccessUnit, Indexer
from mpeg_common import MPEGClock, split_annexb_and_yield_nal

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

def parse_buffering_period_sei(br: BitReader, sps: dict[str, int]) -> dict[str, int]:
    length = sps["initial_cpb_removal_delay_length_minus1"] + 1
    cpb_cnt = sps["cpb_cnt_minus1"]

    br.read_ue() #sps_id
    delays = []

    for _ in range(cpb_cnt + 1):
        delays.append({
            "initial_cpb_removal_delay": br.read_bits(length),
            "initial_cpb_removal_delay_offset": br.read_bits(length),
        })
    return delays

def parse_picture_timing_sei(br: BitReader, sps: dict[str, int]) -> dict[str, int]:
    cpb_len = sps["cpb_removal_delay_length_minus1"] + 1
    dpb_len = sps["dpb_output_delay_length_minus1"] + 1

    pic_timing_data = {
        "cpb_removal_delay": br.read_bits(cpb_len),
        "dpb_output_delay": br.read_bits(dpb_len),
    }
    if sps.get('pic_struct_present_flag', False):
        pic_timing_data['pic_struct'] = br.read_bits(4)
    return pic_timing_data

def parse_sei(rbsp: bytes, sps: dict[str, int]) -> tuple[int, dict[str, int]]:
    """
    This function was written by a LLM and is thereby under MIT License.
    """
    br = BitReader(rbsp)
    results = []

    while br.bitpos + 16 < len(rbsp) * 8:
        payload_type = 0
        while True:
            b = br.read_bits(8)
            payload_type += b
            if b != 0xFF:
                break

        payload_size = 0
        while True:
            b = br.read_bits(8)
            payload_size += b
            if b != 0xFF:
                break

        payload_start = br.bitpos
        payload_end = payload_start + payload_size * 8
        if payload_type == SEI.BufferingPeriod:
            results.append(parse_buffering_period_sei(br, sps))
        if payload_type == SEI.PictureTiming:
            results.append(parse_picture_timing_sei(br, sps))

        br.bitpos = payload_end
    return payload_type, results
####

#%% Primary parser and datastructure
@dataclass
class AVCAccessUnit(AccessUnit):
    primary_pic_type: int | None = None
    sequence_parameter_set: None | dict[str, int] = None
    picture_parameter_set:  None | dict[str, int] = None
    sei:  dict[str, int] = field(default_factory=dict)   # sei_name -> sei_data
    misc: dict[str, int] = field(default_factory=dict)   # user meta

class AVCParser(Parser):
    def __init__(self, fp: Path | str) -> None:
        super().__init__(fp)
        assert (fp := Path(fp)).exists()
        self._fp = fp

    def get_timing_informations(self) -> dict[str, int]:
        """
        Return the AVC stream frame timing information.
        Only value with CFR streams, else you must parse every provided 
        
        Returns: 
        - time_scale: Number of time units per second.
        - num_units_in_tick: Number of time units per field (AVC is field based)
        
        time_scale / num_units_in_tick = fields per second = 2 * frames per second
        """
        au = next(iter(self))
        if au.sequence_parameter_set is None:
            raise RuntimeError("No SPS in first Access Unit.")
        if not au.sequence_parameter_set.get('fixed_frame_rate_flag', False):
            raise RuntimeError("No VUI, no timing information present, or VFR.")
        return {
            'time_scale':au.sequence_parameter_set['time_scale'],
            'num_units_in_tick': au.sequence_parameter_set['num_units_in_tick']
        }

    def parse(self, parse_sps_once: bool = True) -> Generator[AVCAccessUnit, None, None]:
        current_sps = current_access_unit = None
        
        with open(self._fp, 'rb') as fio:
            for nal in split_annexb_and_yield_nal(fio):
                nal_type = NALType(nal[0] & 0x1F)
                sub_type = None
                # remove emulation only for payloads of interest
                match nal_type:
                    case NALType.AUD:
                        rbsp = remove_emulation_prevention(nal[1:])
                        if current_access_unit is not None:
                            yield current_access_unit
                        current_access_unit = AVCAccessUnit(primary_pic_type=nal[1] >> 5, misc={'nals':[]})
                    case NALType.SPS:
                        # Parse SPS once, because the parameters of interest must
                        # be constant (time_scale, nuit, HRD, ps)
                        if not parse_sps_once or current_sps is None:
                            rbsp = remove_emulation_prevention(nal[1:])
                            current_sps = current_access_unit.sequence_parameter_set = parse_sps(rbsp)
                    case NALType.SEI:
                        rbsp = remove_emulation_prevention(nal[1:])
                        sub_type, data = parse_sei(rbsp, current_sps)
                        try: sub_type = SEI(sub_type)
                        except: pass
                        match sub_type:
                            case SEI.BufferingPeriod:
                                current_access_unit.sei[sub_type] = data
                            case SEI.PictureTiming:
                                # maybe report multi-decoder data?
                                current_access_unit.sei[sub_type] = data[0]
                    ####case SEI
                current_access_unit.size += len(nal) + 3
                current_access_unit.misc['nals'].append((nal_type, sub_type))
                ####
            ####
        yield current_access_unit
    ####
####

#%%
class AVCIndexer(Indexer):
    _parser = AVCParser
    def __init__(self, input_file: Path | str, index_file: Path | str):
        super().__init__(input_file, index_file)
        
    @staticmethod
    def get_pts_dts_of_access_unit(
            first_pts: int = MPEGClock.PTS,
        ) -> Generator[tuple[int, int], None, None]:
        """
        Generate DTS/PTS pair from a list or generator of access units
        
        Caller is responsible for discarding the DTS if it is equal to the PTS.

        Parameters
        ----------
        access_units : Iterable[AVCAccessUnit]
            Iterable of Access Units.
        first_pts : int, optional
            First PTS value

        Yields
        ------
        tuple[int, int]
            (dts, pts) pair
        """
        f_cast = lambda x, y: (int(x), int(y))
        
        au = yield
        
        field_duration = MPEGClock.PTS * Fraction(
            au.sequence_parameter_set['num_units_in_tick'],
            au.sequence_parameter_set['time_scale'])

        picture_timing = au.sei[SEI.PictureTiming]
        pts = first_pts
        dts = pts - picture_timing['dpb_output_delay'] * field_duration
        
        last_buffering_sei_ts = first_pts - 2*field_duration
        
        # is the DTS further back in comparison to the default 2-frame one?
        if (dts_shift := (last_buffering_sei_ts - dts)) > 0:
            # (not how we should detect b-pyramid, but whatever)
            print(f"b-pyramid detected: shift DTS by {dts_shift/field_duration} frames.")
            last_buffering_sei_ts -= dts_shift
                
        if dts <= 0 or last_buffering_sei_ts <= 0:
            raise RuntimeError("First PTS offset is unsufficient.")
        
        while True:
            au = yield f_cast(dts, pts)
            if au is None:
                break
            
            picture_timing = au.sei[SEI.PictureTiming]
            dts = last_buffering_sei_ts + (picture_timing['cpb_removal_delay'] * field_duration)
            pts = dts + (picture_timing['dpb_output_delay'] * field_duration)
                 
            if SEI.BufferingPeriod in au.sei:
                last_buffering_sei_ts = dts
        return
    ####
####
