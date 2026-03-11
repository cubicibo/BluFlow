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
from fractions import Fraction
from pathlib import Path

from typing import Generator

from bitstream import BitReader, remove_emulation_prevention as remove_emulation_prevention
from common import Parser, Indexer

from avc_internals import parse_sps, nal_requires_annexb_zero_byte, parse_nal_unit_type, NALType
from mpeg_common import split_annexb_and_yield_nal, yield_sei_units, SEI
from utils import MPEGClock, TSPair, AccessUnit

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
            for nalu in split_annexb_and_yield_nal(fio, f_requires_zero_byte=nal_requires_annexb_zero_byte):
                nal = nalu[4:] if nalu[2] == 0 else nalu[3:]
                nal_type = parse_nal_unit_type(nal[0])
                # remove emulation only for payloads of interest
                match nal_type:
                    case NALType.AUD:
                        rbsp = remove_emulation_prevention(nal[1:])
                        if current_access_unit is not None:
                            yield current_access_unit
                        current_access_unit = AVCAccessUnit(primary_pic_type=nal[1] >> 5, misc={'nals':[]})
                    case NALType.SPS:
                        if not parse_sps_once or current_sps is None:
                            rbsp = remove_emulation_prevention(nal[1:])
                            current_sps = current_access_unit.sequence_parameter_set = parse_sps(rbsp)
                    case NALType.SEI:
                        rbsp = remove_emulation_prevention(nal[1:])
                        for sei_type, br in yield_sei_units(rbsp):
                            match sei_type:
                                case SEI.BufferingPeriod:
                                    current_access_unit.sei[sei_type] = parse_buffering_period_sei(br, current_sps)
                                case SEI.PictureTiming:
                                    current_access_unit.sei[sei_type] = parse_picture_timing_sei(br, current_sps)
                    ####case SEI
                current_access_unit.size += len(nalu)
                current_access_unit.misc['nals'].append((nal_type))
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
        f_cast = lambda x, y: TSPair(int(x), int(y))
        
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
            au = yield f_cast(pts, dts)
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
