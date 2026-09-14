# BluFlow
BluFlow is a Python package to manipulate Transport Streams (.TS, .M2TS), as well as common multimedia bitstreams like H.264, H.265 meant for broadcast or delivery.

## Status
- H.264 and H.265 parsers and indexers are functionals; the bitstreams must carry HRD information.
- Transport Stream (.TS and .M2TS) can be demuxed to elementary streams.
- Packetized Elementary Stream (PES) can be processed per packet, and manipulated.

## Work in progress
- Index files for muxing, partially implemented
- Transport stream muxing
- Audio codecs (AC3 will come first)

## License
The current project is under GPLv3.
