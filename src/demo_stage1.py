"""Stage 1 demonstration: generate 5 WebM samples and convert via CLI."""

import io
import os
import subprocess
import sys
import tempfile

import av
from PIL import Image, ImageDraw

from src.constants import (
    CLI_TIMEOUT_SECONDS,
    FOUR,
    GIF_HEADER_87A,
    GIF_HEADER_89A,
    GIF_HEADER_LEN,
    MAX_GIF_COLORS,
    ONE,
    SAMPLE_COUNT,
    THREE,
    TWO,
    ZERO,
)

SAMPLE_SPECS = (
    ("sample_1_bars.webm", 64, 48, 6, 6, "bars"),
    ("sample_2_gradient.webm", 80, 60, 8, 8, "gradient"),
    ("sample_3_pulse.webm", 96, 72, 10, 10, "pulse"),
    ("sample_4_checker.webm", 128, 96, 8, 12, "checker"),
    ("sample_5_sweep.webm", 160, 120, 10, 10, "sweep"),
)


def _draw_pattern(pattern, width, height, idx, total):
    """Draw a synthetic RGB frame for a sample WebM animation."""
    img = Image.new("RGB", (width, height), (20, 24, 32))
    draw = ImageDraw.Draw(img)
    shift = int((idx * MAX_GIF_COLORS) / max(ONE, total))
    if pattern == "bars":
        bar_w = max(ONE, width // FOUR)
        for col in range(FOUR):
            rgb = ((col * 60 + shift) % MAX_GIF_COLORS, 120, 200)
            draw.rectangle(
                [col * bar_w, ZERO, (col + ONE) * bar_w, height],
                fill=rgb,
            )
    elif pattern == "gradient":
        color = (shift % MAX_GIF_COLORS, 180, (255 - shift) % MAX_GIF_COLORS)
        draw.rectangle([ZERO, ZERO, width, height], fill=color)
    elif pattern == "pulse":
        pad = (idx % THREE) * FOUR + FOUR
        draw.ellipse(
            [pad, pad, width - pad, height - pad],
            fill=(220, 90, 60),
        )
    elif pattern == "checker":
        offset = (idx % TWO) * 16
        for x_pos in range(ZERO, width, 16):
            for y_pos in range(ZERO, height, 16):
                if ((x_pos + y_pos + offset) // 16) % TWO == ZERO:
                    draw.rectangle(
                        [x_pos, y_pos, x_pos + 15, y_pos + 15],
                        fill=(90, 200, 140),
                    )
    else:
        pos_x = int((width - 20) * idx / max(ONE, total - ONE))
        draw.rectangle(
            [pos_x, 10, pos_x + 20, height - 10],
            fill=(80, 170, 240),
        )
    return img


def generate_sample_webm(target_path, width, height, frame_count,
                         fps, pattern):
    """Generate a valid VP8 WebM video file at target_path."""
    with av.open(target_path, mode="w", format="webm") as container:
        stream = container.add_stream("libvpx", rate=fps)
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"
        for idx in range(frame_count):
            pil_img = _draw_pattern(pattern, width, height, idx, frame_count)
            video_frame = av.VideoFrame.from_image(pil_img)
            for packet in stream.encode(video_frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


def inspect_gif_bytes(gif_bytes):
    """Inspect generated GIF bytes and return format summary tuple."""
    header = gif_bytes[:GIF_HEADER_LEN]
    if header not in (GIF_HEADER_87A, GIF_HEADER_89A):
        raise ValueError("Stdout payload is not a valid GIF")
    with Image.open(io.BytesIO(gif_bytes)) as gif_img:
        frame_count = getattr(gif_img, "n_frames", ONE)
        return gif_img.format, gif_img.size, frame_count


def run_demo():
    """Run CLI WebM to GIF converter on 5 synthetic input examples."""
    print("Stage 1 Demonstration: WebM -> GIF CLI Converter")
    print("=" * 60)
    with tempfile.TemporaryDirectory() as tmp_dir:
        for idx, spec in enumerate(SAMPLE_SPECS[:SAMPLE_COUNT], start=ONE):
            name, width, height, count, fps, pattern = spec
            in_path = os.path.join(tmp_dir, name)
            generate_sample_webm(in_path, width, height, count, fps, pattern)
            in_size = os.path.getsize(in_path)
            proc = subprocess.run(
                [sys.executable, "-m", "src.converter", in_path],
                capture_output=True,
                timeout=CLI_TIMEOUT_SECONDS,
                check=False,
            )
            if proc.returncode != ZERO:
                err_msg = proc.stderr.decode("utf-8", errors="replace")
                raise RuntimeError(f"CLI failed for {name}: {err_msg}")
            fmt, size, frames = inspect_gif_bytes(proc.stdout)
            print(
                f"[{idx}/{SAMPLE_COUNT}] {name} ({in_size} B) -> "
                f"stdout {fmt} {size[ZERO]}x{size[ONE]}, "
                f"frames={frames}, bytes={len(proc.stdout)}"
            )
    print("=" * 60)
    print("Stage 1 Demonstration Completed Successfully.")


if __name__ == "__main__":
    run_demo()
