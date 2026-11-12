"""CLI utility converting WebM video files into GIF bytes on stdout."""

import argparse
import io
import os
import sys

import av

from src.constants import (
    DEFAULT_FRAME_DURATION_MS,
    DEFAULT_GIF_FPS,
    MIN_FPS,
    MIN_FRAME_COUNT,
    MS_PER_SECOND,
    ONE,
    ZERO,
)


def _extract_frames(container, max_width=None):
    """Decode all video frames from container as PIL RGB images."""
    frames = []
    for frame in container.decode(video=ZERO):
        img = frame.to_image()
        if max_width is not None and img.width > max_width:
            ratio = max_width / float(img.width)
            new_height = max(ONE, int(img.height * ratio))
            img = img.resize((max_width, new_height))
        frames.append(img.convert("RGB"))
    return frames


def convert_webm_to_gif_bytes(input_path, fps=DEFAULT_GIF_FPS,
                              max_width=None):
    """Read WebM video at input_path and return animated GIF bytes."""
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if fps < MIN_FPS:
        raise ValueError("FPS must be at least 1")
    with av.open(input_path) as container:
        frames = _extract_frames(container, max_width=max_width)
    if len(frames) < MIN_FRAME_COUNT:
        raise ValueError(f"No video frames decoded from: {input_path}")
    duration_ms = max(ONE, int(MS_PER_SECOND / fps))
    if duration_ms <= ZERO:
        duration_ms = DEFAULT_FRAME_DURATION_MS
    buf = io.BytesIO()
    first_frame = frames[ZERO]
    rest_frames = frames[ONE:]
    first_frame.save(
        buf,
        format="GIF",
        save_all=True,
        append_images=rest_frames,
        duration=duration_ms,
        loop=ZERO,
    )
    return buf.getvalue()


def build_parser():
    """Build command-line argument parser for WebM to GIF converter."""
    parser = argparse.ArgumentParser(
        description="Convert WebM video file to GIF on standard output."
    )
    parser.add_argument(
        "input_file",
        help="Path to the input WebM file.",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=DEFAULT_GIF_FPS,
        help="Target GIF frame rate.",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=None,
        help="Optional maximum output width in pixels.",
    )
    return parser


def main(argv=None):
    """Run CLI conversion and write GIF bytes to stdout."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        gif_bytes = convert_webm_to_gif_bytes(
            args.input_file,
            fps=args.fps,
            max_width=args.width,
        )
    except Exception as exc:
        sys.stderr.write(f"Conversion error: {exc}\n")
        return ONE
    sys.stdout.buffer.write(gif_bytes)
    sys.stdout.buffer.flush()
    return ZERO


if __name__ == "__main__":
    raise SystemExit(main())
