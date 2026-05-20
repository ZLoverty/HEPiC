"""Convert a PNG to a multi-resolution .ico file."""

import sys
from pathlib import Path
from PIL import Image


def png_to_ico(src: str, dst: str | None = None):
    src_path = Path(src)
    dst_path = Path(dst) if dst else src_path.with_suffix(".ico")

    img = Image.open(src_path).convert("RGBA")
    img.save(
        dst_path,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Saved: {dst_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/png_to_ico.py <input.png> [output.ico]")
        sys.exit(1)
    png_to_ico(*sys.argv[1:])
