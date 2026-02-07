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

from muxctx import Demux
from streams import ArbitraryTransportStream

import argparse as ap

parser = ap.ArgumentParser()

parser.add_argument('-f', '--folder', type=str)
parser.add_argument('file', type=str)

args = parser.parse_args()
assert (df := Path(args.folder)).exists()
assert (fp := Path(args.file)).exists()

dm_ctx = Demux(ArbitraryTransportStream(fp))
dm_ctx.index_streams('/Users/cibo/Desktop/demux/', tqdm())