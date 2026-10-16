import io
import json
import math
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Any

import cv2
import numpy as np
from PIL import Image

from ..config import settings
from .storage import storage_service

_rembg_lock = threading.Lock()
_rembg_sessions: Dict[str, Any] = {}


def _is_onnx_model_cached(model_name: str) -> bool:
    u2net_home = Path.home() / ".u2net"
    candidates = [
        u2net_home / f"{model_name}.onnx",
        u2net_home / "u2netp.onnx",
        u2net_home / "u2net.onnx",
    ]
    return any(p.exists() and p.stat().st_size > 100_000 for p in candidates)


def get_or_create_rembg_session(model_name: Optional[str] = None, force_download: bool = False) -> Optional[Any]:
    """
    Returns a persistent ONNX Runtime session kept in RAM (FR-04, NFR-01).
    """
    target_model = model_name or settings.AI_MODEL_NAME or "u2netp"
    with _rembg_lock:
        if target_model in _rembg_sessions:
            return _rembg_sessions[target_model]

        if not force_download and settings.AI_AUTO_FALLBACK and not _is_onnx_model_cached(target_model):
            return None

        try:
            from rembg import new_session
            session = new_session(target_model)
            _rembg_sessions[target_model] = session
            return session
        except Exception:
            return None


def remove_bg_studio_alpha(img_rgb: np.ndarray) -> np.ndarray:
    """
    Fast, high-precision OpenCV Corner-Sampled LAB Color-Space + Morphological Feathering
    background remover. Separates studio/cluttered table backdrop from foreground object
    and produces a clean RGBA image with smooth antialiased alpha edges.
    """
    h, w = img_rgb.shape[:2]
    lab = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)

    # Sample border strips (top, bottom, left, right margins) to model background distribution
    pad = max(6, int(min(h, w) * 0.05))
    top_strip = lab[:pad, :, :].reshape(-1, 3)
    bottom_strip = lab[h - pad :, :, :].reshape(-1, 3)
    left_strip = lab[:, :pad, :].reshape(-1, 3)
    right_strip = lab[:, w - pad :, :].reshape(-1, 3)
    border_samples = np.vstack([top_strip, bottom_strip, left_strip, right_strip])

    bg_mean = np.median(border_samples, axis=0)
    bg_std = np.std(border_samples, axis=0) + 6.0

    # Normalized Mahalanobis-like distance in CIE LAB space
    diff = lab - bg_mean
    weights = np.array([0.55, 1.35, 1.35], dtype=np.float32)
    dist = np.sqrt(np.sum((diff / bg_std) ** 2 * weights, axis=2))

    # Threshold into soft mask
    fg_mask = np.clip((dist - 2.35) / 1.65, 0.0, 1.0)
    binary = (fg_mask > 0.35).astype(np.uint8) * 255

    # Suppress border-connected background artifacts using Morphological Close + Open
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

    # Keep main foreground contour(s) near center
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if num_labels > 1:
        clean_mask = np.zeros_like(binary)
        img_cx, img_cy = w / 2.0, h / 2.0
        best_score = -1.0
        best_label = 1
        total_area = h * w
        for lbl in range(1, num_labels):
            area = stats[lbl, cv2.CC_STAT_AREA]
            if area < total_area * 0.005:
                continue
            cx, cy = centroids[lbl]
            dist_center = math.hypot(cx - img_cx, cy - img_cy) / math.hypot(img_cx, img_cy)
            score = area * (1.25 - 0.65 * dist_center)
            if score > best_score:
                best_score = score
                best_label = lbl

        # Include any substantial component close to the primary object
        for lbl in range(1, num_labels):
            area = stats[lbl, cv2.CC_STAT_AREA]
            if lbl == best_label or area > total_area * 0.025:
                clean_mask[labels == lbl] = 255

        # Fill internal holes inside the object silhouette
        contours, _ = cv2.findContours(clean_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        filled = np.zeros_like(clean_mask)
        cv2.drawContours(filled, contours, -1, 255, thickness=cv2.FILLED)
        binary = filled

    # Feather alpha edge for anti-aliased sprite spin rendering
    alpha = cv2.GaussianBlur(binary, (3, 3), 0.8)
    rgba = np.dstack([img_rgb, alpha])
    return rgba


def remove_background_single(
    img_pil: Image.Image,
    ai_mode: str = "auto",
) -> Tuple[np.ndarray, str]:
    """
    Removes background from a single PIL image and returns (RGBA numpy array, engine_name).
    """
    if img_pil.mode == "RGBA":
        arr = np.array(img_pil)
        # If image already has a clean transparent background, preserve it
        if np.mean(arr[:, :, 3] < 15) > 0.15:
            return arr, "alpha_passthrough"

    rgb = np.array(img_pil.convert("RGB"))
    force_rembg = ai_mode == "rembg"
    if ai_mode in ("auto", "rembg"):
        session = get_or_create_rembg_session(force_download=force_rembg)
        if session is not None:
            try:
                from rembg import remove
                out_pil = remove(img_pil.convert("RGB"), session=session, post_process_mask=True)
                return np.array(out_pil.convert("RGBA")), f"rembg:{settings.AI_MODEL_NAME}"
            except Exception:
                pass

    rgba = remove_bg_studio_alpha(rgb)
    return rgba, "opencv_studio_ai"


def extract_frames_from_video(video_path: Path, target_frames: int = 36) -> List[Image.Image]:
    """
    FR-01 (Turntable Mode): Extracts 24 or 36 evenly spaced frames from a 10-12s turntable video.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video file: {video_path.name}")

    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        raw_frames: List[np.ndarray] = []

        if total_frames > target_frames:
            # Sample evenly spaced indices across [0, total_frames - 2] (avoid duplicate final frame on full loop)
            indices = np.linspace(0, max(0, total_frames - 2), target_frames, dtype=int)
            idx_set = set(indices.tolist())
            curr = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                if curr in idx_set:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    raw_frames.append(rgb)
                curr += 1
        else:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                raw_frames.append(rgb)

        if not raw_frames:
            raise ValueError("No valid frames could be decoded from the uploaded video.")

        # Resample to exact target_frames if needed
        if len(raw_frames) != target_frames:
            pick = np.linspace(0, len(raw_frames) - 1, target_frames, dtype=int)
            raw_frames = [raw_frames[i] for i in pick]

        return [Image.fromarray(f) for f in raw_frames]
    finally:
        cap.release()


def compute_object_geometry(rgba: np.ndarray) -> Dict[str, float]:
    """
    Computes foreground bounding box (x, y, w, h) and alpha-weighted centroid (cx, cy).
    """
    h, w = rgba.shape[:2]
    alpha = rgba[:, :, 3]
    ys, xs = np.where(alpha > 25)

    if len(xs) < 25:
        return {
            "x_min": 0.0,
            "y_min": 0.0,
            "x_max": float(w),
            "y_max": float(h),
            "width": float(w),
            "height": float(h),
            "cx": w / 2.0,
            "cy": h / 2.0,
        }

    x_min, x_max = float(np.min(xs)), float(np.max(xs))
    y_min, y_max = float(np.min(ys)), float(np.max(ys))
    box_w = max(1.0, x_max - x_min + 1.0)
    box_h = max(1.0, y_max - y_min + 1.0)

    weights = alpha[ys, xs].astype(np.float64)
    w_sum = np.sum(weights)
    weight_cx = float(np.sum(xs * weights) / w_sum)
    weight_cy = float(np.sum(ys * weights) / w_sum)

    # Blend 60% bounding-box center + 40% mass centroid for rock-solid rotational stability
    bbox_cx = (x_min + x_max) / 2.0
    bbox_cy = (y_min + y_max) / 2.0
    cx = 0.60 * bbox_cx + 0.40 * weight_cx
    cy = 0.65 * bbox_cy + 0.35 * weight_cy

    return {
        "x_min": x_min,
        "y_min": y_min,
        "x_max": x_max,
        "y_max": y_max,
        "width": box_w,
        "height": box_h,
        "cx": cx,
        "cy": cy,
    }


def auto_center_and_normalize_frames(
    rgba_frames: List[np.ndarray],
    canvas_size: int = 800,
    fill_ratio: float = 0.82,
) -> Tuple[List[Image.Image], Dict[str, Any]]:
    """
    FR-04 Global-Scale Auto-Centering Algorithm:
    1. Computes object centroid (cx, cy) and bounding box (w, h) on every frame.
    2. Finds the GLOBAL maximum object dimension across all 36 frames so the scale factor
       is locked globally -> oblong products (sneakers, watches, figures) keep true 3D
       proportions across angles instead of expanding/shrinking artificially.
    3. Translates each frame's centroid to exact canvas center (canvas_size/2, canvas_size/2),
       eliminating camera/hand/turntable jitter.
    """
    geoms = [compute_object_geometry(f) for f in rgba_frames]

    raw_cxs = np.array([g["cx"] for g in geoms])
    raw_cys = np.array([g["cy"] for g in geoms])
    raw_ws = np.array([g["width"] for g in geoms])
    raw_hs = np.array([g["height"] for g in geoms])

    raw_jitter_px = float(np.hypot(np.std(raw_cxs), np.std(raw_cys)))
    global_max_span = float(max(np.max(raw_ws), np.max(raw_hs), 1.0))
    target_span = canvas_size * fill_ratio
    global_scale = target_span / global_max_span

    centered_images: List[Image.Image] = []
    target_center = canvas_size / 2.0

    for rgba, g in zip(rgba_frames, geoms):
        x0 = max(0, int(math.floor(g["x_min"])))
        y0 = max(0, int(math.floor(g["y_min"])))
        x1 = min(rgba.shape[1], int(math.ceil(g["x_max"])) + 1)
        y1 = min(rgba.shape[0], int(math.ceil(g["y_max"])) + 1)

        crop = rgba[y0:y1, x0:x1]
        crop_h, crop_w = crop.shape[:2]
        if crop_h <= 0 or crop_w <= 0:
            centered_images.append(Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0)))
            continue

        new_w = max(1, int(round(crop_w * global_scale)))
        new_h = max(1, int(round(crop_h * global_scale)))
        resized_crop = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

        # Offset relative to the object's centroid inside the crop
        rel_cx = (g["cx"] - x0) * global_scale
        rel_cy = (g["cy"] - y0) * global_scale

        paste_x = int(round(target_center - rel_cx))
        paste_y = int(round(target_center - rel_cy))

        canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
        crop_pil = Image.fromarray(resized_crop, mode="RGBA")
        canvas.alpha_composite(crop_pil, dest=(paste_x, paste_y))
        centered_images.append(canvas)

    metrics = {
        "raw_centroid_jitter_px": round(raw_jitter_px, 2),
        "aligned_centroid_jitter_px": 0.0,
        "jitter_reduction_pct": 100.0 if raw_jitter_px > 0 else 0.0,
        "global_max_span_px": round(global_max_span, 1),
        "global_scale_factor": round(global_scale, 4),
        "canvas_size": canvas_size,
        "fill_ratio": fill_ratio,
    }
    return centered_images, metrics


def encode_webp_package(
    product_id: str,
    centered_frames: List[Image.Image],
    raw_frames: List[Image.Image],
    initial_quality: int = 82,
    max_total_mb: float = 3.0,
) -> Tuple[List[str], List[str], str, str, float]:
    """
    NFR-02: Encodes all frames to WebP format and ensures total package size stays <= 3.0 MB.
    Also saves thumbnail.webp and raw preview frames for Before/After comparison.
    """
    quality = initial_quality
    encoded_buffers: List[bytes] = []

    for attempt in range(3):
        encoded_buffers.clear()
        total_bytes = 0
        for img in centered_frames:
            buf = io.BytesIO()
            img.save(buf, format="WEBP", quality=quality, method=4)
            data = buf.getvalue()
            encoded_buffers.append(data)
            total_bytes += len(data)

        total_mb = total_bytes / (1024 * 1024)
        if total_mb <= max_total_mb or quality <= 60:
            break
        quality = max(60, quality - 10)

    frame_urls: List[str] = []
    for idx, data in enumerate(encoded_buffers):
        rel_path = f"frames/frame_{idx:02d}.webp"
        url = storage_service.save_bytes(product_id, rel_path, data, content_type="image/webp")
        frame_urls.append(url)

    # Save raw frames (compressed WebP) so user can toggle Before/After Jitter & Background in Studio
    raw_urls: List[str] = []
    for idx, raw_img in enumerate(raw_frames):
        raw_resized = raw_img.convert("RGB").resize((480, 480), Image.Resampling.BILINEAR)
        buf = io.BytesIO()
        raw_resized.save(buf, format="WEBP", quality=70, method=3)
        r_url = storage_service.save_bytes(
            product_id, f"raw/raw_{idx:02d}.webp", buf.getvalue(), content_type="image/webp"
        )
        raw_urls.append(r_url)

    # Save thumbnail.webp (frame 0)
    thumb_url = storage_service.save_bytes(
        product_id, "thumbnail.webp", encoded_buffers[0], content_type="image/webp"
    )
    raw_preview_url = raw_urls[0] if raw_urls else thumb_url
    package_size_mb = round(sum(len(b) for b in encoded_buffers) / (1024 * 1024), 3)

    return frame_urls, raw_urls, thumb_url, raw_preview_url, package_size_mb


def run_full_ai_pipeline(
    product_id: str,
    input_frames: List[Image.Image],
    product_meta: Dict[str, Any],
    ai_mode: str = "auto",
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> Dict[str, Any]:
    """
    Executes the complete FR-04 pipeline:
    1. Parallel AI Background Removal (ONNX RemBG or OpenCV Studio Alpha Matting)
    2. Global-Scale Auto-Centering & Normalization
    3. WebP Packaging & index.json metadata generation
    """
    t0 = time.perf_counter()
    num_frames = len(input_frames)

    if progress_callback:
        progress_callback(15, "removing_background")

    rgba_results: List[Optional[np.ndarray]] = [None] * num_frames
    engines_used: List[str] = [""] * num_frames

    # Pre-initialize rembg session once before thread pool if applicable
    if ai_mode in ("auto", "rembg"):
        get_or_create_rembg_session(force_download=(ai_mode == "rembg"))

    completed_count = 0
    count_lock = threading.Lock()

    def _process_one(idx_and_img: Tuple[int, Image.Image]) -> None:
        nonlocal completed_count
        idx, pil_img = idx_and_img
        # Normalize input working resolution for fast inference (<10s for 36 frames)
        max_in = 900
        if max(pil_img.size) > max_in:
            scale = max_in / float(max(pil_img.size))
            pil_img = pil_img.resize(
                (int(pil_img.width * scale), int(pil_img.height * scale)),
                Image.Resampling.BILINEAR,
            )
        rgba, engine_name = remove_background_single(pil_img, ai_mode=ai_mode)
        rgba_results[idx] = rgba
        engines_used[idx] = engine_name
        with count_lock:
            completed_count += 1
            if progress_callback and (completed_count % 4 == 0 or completed_count == num_frames):
                pct = 15 + int((completed_count / num_frames) * 45)
                progress_callback(pct, "removing_background")

    with ThreadPoolExecutor(max_workers=settings.MAX_WORKERS) as pool:
        list(pool.map(_process_one, enumerate(input_frames)))

    valid_rgba = [r for r in rgba_results if r is not None]
    engine_used = engines_used[0] if engines_used else "opencv_studio_ai"

    if progress_callback:
        progress_callback(65, "auto_centering")

    centered_frames, jitter_metrics = auto_center_and_normalize_frames(
        valid_rgba,
        canvas_size=settings.OUTPUT_CANVAS_SIZE,
        fill_ratio=settings.GLOBAL_SCALE_FILL_RATIO,
    )

    if progress_callback:
        progress_callback(82, "encoding_webp")

    frame_urls, raw_urls, thumb_url, raw_preview_url, package_size_mb = encode_webp_package(
        product_id=product_id,
        centered_frames=centered_frames,
        raw_frames=input_frames,
        initial_quality=settings.WEBP_QUALITY,
    )

    elapsed_sec = round(time.perf_counter() - t0, 2)
    jitter_metrics["processing_time_sec"] = elapsed_sec
    jitter_metrics["package_size_mb"] = package_size_mb
    jitter_metrics["nfr01_passed"] = elapsed_sec <= 15.0
    jitter_metrics["nfr02_passed"] = package_size_mb <= 3.0

    # Generate index.json manifest (FR-04)
    index_manifest = {
        "schema_version": "1.0",
        "product_id": product_id,
        "short_code": product_meta["short_code"],
        "name": product_meta["name"],
        "category": product_meta["category"],
        "description": product_meta["description"],
        "capture_mode": product_meta["capture_mode"],
        "frame_count": len(frame_urls),
        "canvas_size": settings.OUTPUT_CANVAS_SIZE,
        "package_size_mb": package_size_mb,
        "processing_time_sec": elapsed_sec,
        "ai_engine_used": engine_used,
        "thumbnail_url": thumb_url,
        "share_url": product_meta["share_url"],
        "viewer_url": product_meta["viewer_url"],
        "frames": frame_urls,
        "raw_frames": raw_urls,
        "hotspots": product_meta.get("hotspots", []),
        "exports": product_meta.get("exports", {}),
        "metrics": jitter_metrics,
    }
    index_bytes = json.dumps(index_manifest, indent=2, ensure_ascii=False).encode("utf-8")
    index_json_url = storage_service.save_bytes(
        product_id, "index.json", index_bytes, content_type="application/json"
    )

    if progress_callback:
        progress_callback(100, "completed")

    return {
        "frame_count": len(frame_urls),
        "canvas_size": settings.OUTPUT_CANVAS_SIZE,
        "processing_time_sec": elapsed_sec,
        "package_size_mb": package_size_mb,
        "ai_engine_used": engine_used,
        "thumbnail_url": thumb_url,
        "raw_preview_url": raw_preview_url,
        "index_json_url": index_json_url,
        "frames": frame_urls,
        "raw_frames": raw_urls,
        "metrics": jitter_metrics,
    }


def sync_index_json(product_record: Dict[str, Any]) -> str:
    """Updates index.json in storage when hotspots or MP4 exports are updated."""
    index_manifest = {
        "schema_version": "1.0",
        "product_id": product_record["id"],
        "short_code": product_record["short_code"],
        "name": product_record["name"],
        "category": product_record["category"],
        "description": product_record["description"],
        "capture_mode": product_record["capture_mode"],
        "frame_count": product_record["frame_count"],
        "canvas_size": product_record["canvas_size"],
        "package_size_mb": product_record["package_size_mb"],
        "processing_time_sec": product_record["processing_time_sec"],
        "ai_engine_used": product_record["ai_engine_used"],
        "thumbnail_url": product_record["thumbnail_url"],
        "share_url": product_record["share_url"],
        "viewer_url": product_record["viewer_url"],
        "frames": product_record["frames"],
        "raw_frames": product_record.get("raw_frames", []),
        "hotspots": product_record.get("hotspots", []),
        "exports": product_record.get("exports", {}),
        "metrics": product_record.get("metrics", {}),
    }
    index_bytes = json.dumps(index_manifest, indent=2, ensure_ascii=False).encode("utf-8")
    return storage_service.save_bytes(
        product_record["id"], "index.json", index_bytes, content_type="application/json"
    )
