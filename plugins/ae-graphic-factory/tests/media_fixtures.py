"""Synthetic test media, generated without external codecs or user assets."""
import math
import struct
import zlib
from pathlib import Path


def make_png(path: Path, width=160, height=90):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    rows = b"".join(b"\x00" + bytes((24, 48, 90)) * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    return path


def make_av_avi(path: Path, width=108, height=192, frames=150, fps=30, audio=True):
    """Indexed AVI: uncompressed BGR + 48 kHz mono 16-bit PCM, 440 Hz test tone."""
    def chunk(tag, data):
        return tag + struct.pack("<I", len(data)) + data + (b"\x00" if len(data) % 2 else b"")
    def listing(tag, data):
        return chunk(b"LIST", tag + data)
    row_size = (width * 3 + 3) // 4 * 4
    frame_size = row_size * height
    rate = 48000
    samples_per_frame = rate // fps
    avih = struct.pack("<14I", round(1e6 / fps), frame_size * fps + rate * 2, 0, 0x10,
                       frames, 0, 2 if audio else 1, frame_size, width, height, 0, 0, 0, 0)
    video_header = struct.pack("<4s4sIHH8I4h", b"vids", b"DIB ", 0, 0, 0, 0, 1, fps, 0,
                               frames, frame_size, 0xFFFFFFFF, 0, 0, 0, width, height)
    video_format = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, frame_size, 0, 0, 0, 0)
    streams = listing(b"strl", chunk(b"strh", video_header) + chunk(b"strf", video_format))
    if audio:
        audio_header = struct.pack("<4s4sIHH8I4h", b"auds", b"\x00" * 4, 0, 0, 0, 0, 2, rate * 2, 0,
                                   frames * samples_per_frame, samples_per_frame * 2, 0xFFFFFFFF, 2, 0, 0, 0, 0)
        audio_format = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
        streams += listing(b"strl", chunk(b"strh", audio_header) + chunk(b"strf", audio_format))
    chunks = []
    indices = []
    offset = 4
    for frame in range(frames):
        row = bytes((50, 80 + frame % 100, 160)) * width + bytes(row_size - width * 3)
        parts = [(b"00db", row * height)]
        if audio:
            pcm = b"".join(struct.pack("<h", round(4000 * math.sin(2 * math.pi * 440 * sample / rate)))
                           for sample in range(frame * samples_per_frame, (frame + 1) * samples_per_frame))
            parts.append((b"01wb", pcm))
        for tag, data in parts:
            block = chunk(tag, data)
            indices.append(struct.pack("<4sIII", tag, 0x10, offset, len(data)))
            chunks.append(block)
            offset += len(block)
    payload = b"AVI " + listing(b"hdrl", chunk(b"avih", avih) + streams)
    payload += listing(b"movi", b"".join(chunks)) + chunk(b"idx1", b"".join(indices))
    path.write_bytes(b"RIFF" + struct.pack("<I", len(payload)) + payload)
    return path


if __name__ == "__main__":
    root = Path(__file__).parent / "fixtures"
    make_png(root / "reference-card.png")
    make_png(root / "icon-reference.png", 64, 64)
