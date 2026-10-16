import tempfile
from pathlib import Path
from typing import Dict, Any, Tuple
import cv2
import numpy as np
from PIL import Image, ImageDraw

from .storage import storage_service


def _build_studio_background(width: int, height: int, theme: str = "studio_dark") -> np.ndarray:
    """Creates a clean radial studio gradient background with contact shadow for MP4 showcase."""
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    cx, cy = width * 0.5, height * 0.48
    dist = np.hypot((xx - cx) / (width * 0.65), (yy - cy) / (height * 0.55))
    dist = np.clip(dist, 0.0, 1.4)

    if theme == "studio_light":
        r = np.clip(250 - 28 * dist, 200, 255)
        g = np.clip(251 - 28 * dist, 202, 255)
        b = np.clip(254 - 24 * dist, 208, 255)
    elif theme == "warm_sand":
        r = np.clip(246 - 30 * dist, 195, 252)
        g = np.clip(238 - 32 * dist, 185, 244)
        b = np.clip(224 - 34 * dist, 170, 232)
    else:
        # studio_dark (default premium showcase)
        r = np.clip(38 - 22 * dist, 12, 45)
        g = np.clip(43 - 24 * dist, 14, 52)
        b = np.clip(62 - 30 * dist, 20, 72)

    bg = np.dstack([r, g, b]).astype(np.uint8)

    # Subtle floor shadow ellipse below the centered product
    shadow_y = int(height * 0.76) if height > width else int(height * 0.84)
    shadow_layer = bg.copy()
    cv2.ellipse(
        shadow_layer,
        (int(width * 0.5), shadow_y),
        (int(width * 0.28), int(width * 0.055)),
        0,
        0,
        360,
        (8, 10, 16) if theme == "studio_dark" else (175, 180, 190),
        thickness=-1,
        lineType=cv2.LINE_AA,
    )
    bg = cv2.addWeighted(shadow_layer, 0.45, bg, 0.55, 0)
    return bg


def export_product_mp4(
    product_record: Dict[str, Any],
    aspect_ratio: str = "9:16",
    loops: int = 2,
    fps: int = 24,
    bg_theme: str = "studio_dark",
) -> Tuple[str, str]:
    """
    FR-06: Renders a 360-degree rotating MP4 video (9:16 for Shopee Video / TikTok Shop or 1:1 Square)
    from the processed WebP frames and returns (export_key, public_url).
    """
    product_id = product_record["id"]
    p_dir = storage_service.get_product_dir(product_id)
    frames_dir = p_dir / "frames"

    webp_files = sorted(frames_dir.glob("frame_*.webp"))
    if not webp_files:
        raise ValueError("No processed WebP frames found for this product.")

    if aspect_ratio == "1:1":
        out_w, out_h = 800, 800
        ratio_key = "mp4_1_1"
        filename = "showcase_1x1.mp4"
    else:
        out_w, out_h = 720, 1280
        ratio_key = "mp4_9_16"
        filename = "showcase_9x16.mp4"

    bg_rgb = _build_studio_background(out_w, out_h, theme=bg_theme)
    bg_pil_base = Image.fromarray(bg_rgb, mode="RGB")

    # Add header/footer branding badge on 9:16 vertical videos
    draw = ImageDraw.Draw(bg_pil_base)
    text_color = (240, 244, 255) if bg_theme == "studio_dark" else (28, 34, 48)
    sub_color = (148, 163, 184) if bg_theme == "studio_dark" else (100, 116, 139)

    title_ascii = product_record.get("name", "Pocket 3D Showcase")[:38]
    draw.text((36, 42), "POCKET 3D SHOWCASE • 360 SPIN", fill=sub_color)
    draw.text((36, 68), title_ascii, fill=text_color)

    target_obj_size = int(min(out_w, out_h) * 0.88)
    paste_x = (out_w - target_obj_size) // 2
    paste_y = (out_h - target_obj_size) // 2

    loaded_frames = []
    for wf in webp_files:
        img = Image.open(wf).convert("RGBA")
        if img.size != (target_obj_size, target_obj_size):
            img = img.resize((target_obj_size, target_obj_size), Image.Resampling.LANCZOS)
        loaded_frames.append(img)

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(tmp_path), fourcc, float(fps), (out_w, out_h))
        if not writer.isOpened():
            raise RuntimeError("Failed to initialize OpenCV MP4 VideoWriter.")

        total_frames = len(loaded_frames) * loops
        for step in range(total_frames):
            frame_rgba = loaded_frames[step % len(loaded_frames)]
            canvas = bg_pil_base.copy().convert("RGBA")
            canvas.alpha_composite(frame_rgba, dest=(paste_x, paste_y))

            # Draw subtle angle progress indicator bar at bottom
            progress_ratio = (step % len(loaded_frames)) / float(max(1, len(loaded_frames) - 1))
            frame_bgr = cv2.cvtColor(np.array(canvas.convert("RGB")), cv2.COLOR_RGB2BGR)

            bar_y = out_h - 32
            bar_x0, bar_x1 = 48, out_w - 48
            cv2.line(frame_bgr, (bar_x0, bar_y), (bar_x1, bar_y), (90, 100, 120), 3, cv2.LINE_AA)
            active_x = int(bar_x0 + (bar_x1 - bar_x0) * progress_ratio)
            cv2.line(frame_bgr, (bar_x0, bar_y), (active_x, bar_y), (245, 185, 65), 4, cv2.LINE_AA)

            writer.write(frame_bgr)

        writer.release()
        mp4_bytes = tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)

    url = storage_service.save_bytes(
        product_id, f"exports/{filename}", mp4_bytes, content_type="video/mp4"
    )
    return ratio_key, url
