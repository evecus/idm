"""Generate simple placeholder icons for the extension."""
import os

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

icons_dir = os.path.join(os.path.dirname(__file__), "extension", "icons")
os.makedirs(icons_dir, exist_ok=True)

def make_icon(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Background circle
    margin = size // 8
    draw.ellipse([margin, margin, size - margin, size - margin], fill=(13, 110, 253, 255))
    # Arrow down
    cx = size // 2
    aw = size // 3
    ah = size // 3
    ay = size // 3
    # Arrow body
    body_w = aw // 3
    draw.rectangle([cx - body_w, ay, cx + body_w, ay + ah], fill="white")
    # Arrow head
    pts = [
        (cx - aw // 2, ay + ah),
        (cx + aw // 2, ay + ah),
        (cx, ay + ah + ah // 2),
    ]
    draw.polygon(pts, fill="white")
    return img

if HAS_PIL:
    for sz in [16, 32, 48, 128]:
        img = make_icon(sz)
        path = os.path.join(icons_dir, f"icon{sz}.png")
        img.save(path)
        print(f"Created {path}")
else:
    # Create minimal 1x1 PNG as placeholder
    import struct, zlib
    def make_minimal_png(size):
        def write_chunk(tag, data):
            c = zlib.crc32(tag + data) & 0xffffffff
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", c)
        
        w = h = size
        ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
        raw = b""
        for y in range(h):
            raw += b"\x00"
            for x in range(w):
                r = int(13 + (x / w) * 50)
                g = int(110 + (y / h) * 30)
                b = 253
                raw += bytes([r, g, b])
        compressed = zlib.compress(raw)
        
        return (b"\x89PNG\r\n\x1a\n"
                + write_chunk(b"IHDR", ihdr)
                + write_chunk(b"IDAT", compressed)
                + write_chunk(b"IEND", b""))
    
    for sz in [16, 32, 48, 128]:
        path = os.path.join(icons_dir, f"icon{sz}.png")
        with open(path, "wb") as f:
            f.write(make_minimal_png(sz))
        print(f"Created placeholder {path}")

print("Icons generated successfully.")
