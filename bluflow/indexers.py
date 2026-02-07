#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Feb  7 21:54:12 2026

@author: cibo
"""

from pathlib import Path
from typing import Iterable
from parsers.common import AccessUnit, Parser
        

class AVCIndexer(Indexer):
    def index(self) -> bool:
        
        return True
    
    def generate_pts_dts_from(
            access_units: Iterable[AVCAccessUnit],
            first_pts: int = 90000,
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
            (dts, pts) pair, 33-bit each
        """
        xts_max = (1 << 33) - 1
        f_to_mpegts33 = lambda x, y: (int(x) & xts_max, int(y) & xts_max)
        
        au_iterator = iter(access_units)
        first_au = next(au_iterator)
        
        field_duration = MPEGTSClock.PTS * Fraction(
            first_au.sequence_parameter_set['num_units_in_tick'],
            first_au.sequence_parameter_set['time_scale'])

        picture_timing = first_au.sei[SEI.PictureTiming]
        pts = first_pts
        dts = pts - picture_timing['dpb_output_delay'] * field_duration
        
        last_buffering_sei_ts = first_pts - 2*field_duration
        
        # is the DTS further back in comparison to the default 2-frame one?
        if (dts_shift := (last_buffering_sei_ts - dts)) > 0:
            # (not how we should detect b-pyramid, but whatever)
            print(f"b-pyramid detected: shift DTS by {dts_shift/field_duration} frames.")
            last_buffering_sei_ts -= dts_shift
        
        yield f_to_mpegts33(dts, pts)
        
        if dts <= 0 or last_buffering_sei_ts <= 0:
            raise RuntimeError("First PTS offset is unsufficient.")

        for n, au in enumerate(au_iterator, 1):
            picture_timing = au.sei[SEI.PictureTiming]
            dts = last_buffering_sei_ts + (picture_timing['cpb_removal_delay'] * field_duration)
            pts = dts + (picture_timing['dpb_output_delay'] * field_duration)
                 
            if SEI.BufferingPeriod in au.sei:
                last_buffering_sei_ts = dts
                
            yield f_to_mpegts33(dts, pts)
        return

class PGSIndexer:
    ...