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
from utils import MPEGClock, TSPair, AccessUnit

from mpeg_common import split_annexb_and_yield_nal, yield_sei_units, SEI
from hevc_internals import parse_sps, parse_vps, NALUnitType, parse_nal_unit_header, nal_requires_annexb_zero_byte

def parse_buffering_period_sei(br: BitReader, sps: dict[str, int]) -> dict[str, int]:
    buff_sei = {}

    buff_sei['bp_seq_parameter_set_id'] = br.read_ue()
    if not sps['vui']['vui_hrd_parameters_present_flag']:
        raise RuntimeError("Found Buffering SEI but HRD parameters missing.")
    hrd_params = sps['vui']['hrd_parameters'] # must be present
    
    initial_cpb_removal_delay_length = 1 + hrd_params['initial_cpb_removal_delay_length_minus1']
    au_cpb_removal_delay_length = 1 + hrd_params['au_cpb_removal_delay_length_minus1']
    dpb_removal_delay_length = 1 + hrd_params['dpb_output_delay_length_minus1']
    
    sub_pic_hrd_params_present_flag = hrd_params['sub_pic_hrd_params_present_flag']
    irap_cpb_params_present_flag = False if sub_pic_hrd_params_present_flag else br.read_bit()

    if irap_cpb_params_present_flag:
        buff_sei['cpb_delay_offset'] = br.read_bits(au_cpb_removal_delay_length)
        buff_sei['dpb_delay_offset'] = br.read_bits(dpb_removal_delay_length)
    else:
        irap_cpb_params_present_flag = False
        buff_sei['cpb_delay_offset'] = buff_sei['dpb_delay_offset'] = 0
    
    buff_sei['concatenation_flag'] = br.read_bit()
    buff_sei['au_cpb_removal_delay_delta_minus1'] = br.read_bits(au_cpb_removal_delay_length)
    
    if hrd_params['nal_hrd_parameters_present_flag']:
        layers = []
        for layer_hrd_params in hrd_params['sub_layer_hrd_parameters']:
            cpbs = []
            for CpbCount in range(layer_hrd_params['cpb_cnt_minus1']+1): 
                tid_params = {
                    'nal_initial_cpb_removal_delay': br.read_bits(initial_cpb_removal_delay_length),
                    'nal_initial_cpb_removal_offset':br.read_bits(initial_cpb_removal_delay_length),
                }
                if sub_pic_hrd_params_present_flag or irap_cpb_params_present_flag:
                    tid_params['nal_initial_alt_cpb_removal_delay'] = br.read_bits(initial_cpb_removal_delay_length)
                    tid_params['nal_initial_alt_cpb_removal_offset']= br.read_bits(initial_cpb_removal_delay_length)
                cpbs.append(tid_params)
            layers.append(cpbs)
        buff_sei |= {'NalHrdBp': layers}
    if hrd_params['vcl_hrd_parameters_present_flag']:
        raise NotImplementedError("VCL HRD not supported")
    return buff_sei

def parse_picture_timing_sei(br: BitReader, sps: dict[str, int]) -> dict[str, int]:
    vui = sps['vui']
    
    pic_timing = {}
    if vui['frame_field_info_present_flag']:
        pic_timing['pic_struct'] = br.read_bits(4)
        pic_timing['source_scan_type'] = br.read_bits(2)
        pic_timing['duplicate_flag'] = br.read_bits(1)
        
    hrd_params = vui['hrd_parameters']
    CpbDpbDelaysPresentFlag = hrd_params['nal_hrd_parameters_present_flag'] or hrd_params['vcl_hrd_parameters_present_flag']
    if CpbDpbDelaysPresentFlag:
        au_cpb_removal_delay_length = 1 + hrd_params['au_cpb_removal_delay_length_minus1']
        dpb_output_delay_length = 1 + hrd_params['dpb_output_delay_length_minus1']
        
        pic_timing['au_cpb_removal_delay_minus1'] = br.read_bits(au_cpb_removal_delay_length)
        pic_timing['pic_dpb_output_delay'] = br.read_bits(dpb_output_delay_length)
        
        if vui['hrd_parameters']['sub_pic_hrd_params_present_flag']:
            raise NotImplementedError("Sub pic HRD not implemneted")   
    return pic_timing

#%% Primary parser and datastructure
@dataclass
class HEVCAccessUnit(AccessUnit):
    pic_type: int | None = None
    video_parameter_set: None | dict[str, ...] = None
    sequence_parameter_set: None | dict[str, ...] = None
    sei:  dict[str, dict[str, ...]] = field(default_factory=dict)   # sei_name -> sei_data
    misc: dict[str, ...] = field(default_factory=dict)   # user meta

class HEVCParser(Parser):
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
        vui = au.sequence_parameter_set.get('vui', {})
        if (hrd_parameters := vui.get('hrd_parameters', {})) is None:
            raise RuntimeError("No VUI or no HRD parameters.")
        
        for sublayer_hrd in hrd_parameters['sub_layer_hrd_parameters']:
            if sublayer_hrd['fixed_pic_rate_general_flag'] is False:
                raise RuntimeError("VFR HEVC stream detected, not allowed.")
        return {
            'time_scale': vui['vui_time_scale'],
            'num_units_in_tick': vui['vui_num_units_in_tick']
        }

    def parse(self, parse_headers_once: bool = True) -> Generator[HEVCAccessUnit, None, None]:
        current_vps = current_sps = current_access_unit = None
                
        with open(self._fp, 'rb') as fio:
            for nalu in split_annexb_and_yield_nal(fio, nal_requires_annexb_zero_byte):
                # drop start_code to ease indexing
                nal = nalu[4:] if nalu[2] == 0 else nalu[3:]
                nal_unit_type, nuh_layer_id, nuh_temporal_id_plus1 = parse_nal_unit_header(nal)
                match nal_unit_type:
                    case NALUnitType.AUD_NUT:
                        print(list(map(hex, nal)), len(nal))
                        rbsp = BitReader(remove_emulation_prevention(nal[2:]))
                        if current_access_unit is not None:
                            yield current_access_unit
                        current_access_unit = HEVCAccessUnit(pic_type=nal[1] >> 5, misc={'nals':[]})
                    case NALUnitType.VPS_NUT:
                        if not parse_headers_once or current_vps is None:
                            rbsp = BitReader(remove_emulation_prevention(nal[2:]))
                            current_vps = current_access_unit.video_parameter_set = parse_vps(rbsp)
                            if current_vps['vps_max_layer_id'] > 0:
                                raise NotImplementedError("HEVC sublayers not supported.")
                    case NALUnitType.SPS_NUT:
                        if not parse_headers_once or current_sps is None:
                            rbsp = BitReader(remove_emulation_prevention(nal[2:]))
                            current_sps = current_access_unit.sequence_parameter_set = parse_sps(rbsp)
                    case NALUnitType.SEI_NUT:
                        rbsp = remove_emulation_prevention(nal[2:])
                        for sei_type, br in yield_sei_units(rbsp):
                            match sei_type:
                                case SEI.BufferingPeriod:
                                    current_access_unit.sei[sei_type] = parse_buffering_period_sei(br, current_sps)
                                case SEI.PictureTiming:
                                    current_access_unit.sei[sei_type] = parse_picture_timing_sei(br, current_sps)
                    ####case SEI
                current_access_unit.size += len(nalu)
                current_access_unit.misc['nals'].append(nal_unit_type)
                ####
            ####
        yield current_access_unit
    ####
####

#%%
class HEVCIndexer(Indexer):
    _parser = HEVCParser
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
