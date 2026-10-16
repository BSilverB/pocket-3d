import secrets
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings, STORAGE_DIR, UPLOADS_STORAGE_DIR, WEB_VIEWER_DIR
from .database import (
    create_product,
    delete_product_record,
    get_product,
    get_product_by_short_code,
    init_db,
    list_products,
    update_product,
)
from .schemas import (
    DemoGenerateRequest,
    HotspotCreateRequest,
    HotspotsBulkUpdateRequest,
    ProductResponse,
    VideoExportRequest,
)
from .services.ai_pipeline import _is_onnx_model_cached, sync_index_json
from .services.demo_generator import DEMO_PRESETS, generate_synthetic_product_frames
from .services.queue_worker import queue_worker
from .services.storage import storage_service
from .services.video_exporter import export_product_mp4


def _generate_short_code() -> str:
    alphabet = "23456789abcdefghjkmnpqrstuvwxyz"
    return "".join(secrets.choice(alphabet) for _ in range(7))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Auto-seed a ready-to-spin 360° demo product if database is empty so user can test immediately
    existing = list_products()
    if not existing:
        try:
            _seed_initial_demo_product()
        except Exception as exc:
            print(f"[Startup Seed Warning]: {exc}")
    yield


def _seed_initial_demo_product() -> None:
    product_id = str(uuid.uuid4())
    short_code = "air360x"
    frames, preset_info = generate_synthetic_product_frames(
        preset="sneaker", frame_count=36, canvas_size=640
    )
    record = {
        "id": product_id,
        "short_code": short_code,
        "name": preset_info["name"],
        "category": preset_info["category"],
        "description": preset_info["description"],
        "capture_mode": "demo_seeded",
        "target_frames": 36,
        "canvas_size": settings.OUTPUT_CANVAS_SIZE,
        "status": "queued",
        "progress": 5,
        "stage": "queued",
        "share_url": f"/s/{short_code}",
        "viewer_url": f"/viewer/{product_id}",
        "hotspots": preset_info["default_hotspots"],
    }
    create_product(record)
    queue_worker.enqueue_pil_frames_job(product_id, frames, ai_mode="auto")


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Pocket 3D Showcase - 360° Sprite Spin Capture, AI Background Removal, Auto-Centering & Web Viewer API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount storage directory for public read-only WebP & index.json delivery (NFR-04)
app.mount("/storage", StaticFiles(directory=str(STORAGE_DIR)), name="storage")

# Mount static assets for Web Viewer & Studio
if WEB_VIEWER_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(WEB_VIEWER_DIR)), name="web_assets")


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "app_name": settings.APP_NAME,
        "version": "1.0.0",
        "queue_backend": queue_worker.active_mode,
        "storage_backend": storage_service.backend,
        "ai_default_model": settings.AI_MODEL_NAME,
        "onnx_model_cached": _is_onnx_model_cached(settings.AI_MODEL_NAME),
        "canvas_size": settings.OUTPUT_CANVAS_SIZE,
        "webp_quality": settings.WEBP_QUALITY,
        "nfr_targets": {
            "max_processing_time_sec": 15.0,
            "max_package_size_mb": 3.0,
            "max_initial_load_sec": 2.0,
        },
    }


@app.get("/api/products", response_model=List[ProductResponse])
def api_list_products():
    return list_products()


@app.get("/api/products/{product_id}", response_model=ProductResponse)
def api_get_product(product_id: str):
    item = get_product(product_id)
    if not item:
        item = get_product_by_short_code(product_id)
    if not item:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm 360°.")
    return item


@app.get("/api/s/{short_code}", response_model=ProductResponse)
def api_get_by_short_code(short_code: str):
    item = get_product_by_short_code(short_code)
    if not item:
        raise HTTPException(status_code=404, detail="Không tìm thấy liên kết 360° này.")
    return item


@app.post("/api/products/demo", response_model=ProductResponse)
def api_generate_demo_product(req: DemoGenerateRequest):
    """
    Synthesizes a 24 or 36-angle 3D product capture with simulated hand/turntable jitter
    and background, then runs it through the full AI Background Removal + Global-Scale Auto-Centering pipeline.
    """
    frame_count = 24 if req.frame_count == 24 else 36
    preset_key = req.preset if req.preset in DEMO_PRESETS else "sneaker"
    frames, preset_info = generate_synthetic_product_frames(
        preset=preset_key, frame_count=frame_count, canvas_size=640
    )

    product_id = str(uuid.uuid4())
    short_code = _generate_short_code()
    record = {
        "id": product_id,
        "short_code": short_code,
        "name": req.name or preset_info["name"],
        "category": req.category or preset_info["category"],
        "description": preset_info["description"],
        "capture_mode": f"demo_{preset_key}",
        "target_frames": frame_count,
        "canvas_size": settings.OUTPUT_CANVAS_SIZE,
        "status": "processing",
        "progress": 5,
        "stage": "queued",
        "share_url": f"/s/{short_code}",
        "viewer_url": f"/viewer/{product_id}",
        "hotspots": preset_info["default_hotspots"],
    }
    created = create_product(record)
    queue_worker.enqueue_pil_frames_job(product_id, frames, ai_mode=req.ai_mode)
    return created


@app.post("/api/products/capture-images", response_model=ProductResponse)
async def api_capture_images(
    name: str = Form("Sản phẩm 360° Mới"),
    category: str = Form("Sneakers / Phụ kiện"),
    description: str = Form(""),
    capture_mode: str = Form("manual_gyro"),
    ai_mode: str = Form("auto"),
    files: List[UploadFile] = File(...),
):
    """
    FR-01 (Manual Gyro Mode) & FR-03 (Ingestion & Queue):
    Accepts multi-angle images (e.g., 24 or 36 angles) from the Flutter Mobile App or Web Studio.
    """
    if len(files) < 4:
        raise HTTPException(
            status_code=400,
            detail="Cần tối thiểu 4 ảnh góc độ (khuyến nghị 24 hoặc 36 góc) để tạo khung xoay 360°.",
        )

    product_id = str(uuid.uuid4())
    short_code = _generate_short_code()
    upload_dir = UPLOADS_STORAGE_DIR / product_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: List[Path] = []
    for idx, up in enumerate(files):
        ext = Path(up.filename or "frame.jpg").suffix or ".jpg"
        dest = upload_dir / f"raw_{idx:03d}{ext}"
        content = await up.read()
        dest.write_bytes(content)
        saved_paths.append(dest)

    record = {
        "id": product_id,
        "short_code": short_code,
        "name": name,
        "category": category,
        "description": description,
        "capture_mode": capture_mode,
        "target_frames": len(saved_paths),
        "canvas_size": settings.OUTPUT_CANVAS_SIZE,
        "status": "queued",
        "progress": 5,
        "stage": "queued",
        "share_url": f"/s/{short_code}",
        "viewer_url": f"/viewer/{product_id}",
        "hotspots": [],
    }
    created = create_product(record)
    queue_worker.enqueue_image_batch_job(product_id, saved_paths, ai_mode=ai_mode)
    return created


@app.post("/api/products/capture-video", response_model=ProductResponse)
async def api_capture_video(
    name: str = Form("Sản phẩm Bàn xoay 360°"),
    category: str = Form("Đồng hồ / Figure / Giày"),
    description: str = Form(""),
    target_frames: int = Form(36),
    ai_mode: str = Form("auto"),
    video: UploadFile = File(...),
):
    """
    FR-01 (Turntable Mode) & FR-03 (Ingestion & Queue):
    Accepts a 10-12s video recorded while the product rotates on an electric turntable,
    automatically extracts 24 or 36 evenly spaced frames, removes background, and auto-centers.
    """
    product_id = str(uuid.uuid4())
    short_code = _generate_short_code()
    upload_dir = UPLOADS_STORAGE_DIR / product_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(video.filename or "turntable.mp4").suffix or ".mp4"
    video_path = upload_dir / f"turntable_input{ext}"
    content = await video.read()
    video_path.write_bytes(content)

    clean_target = 24 if target_frames == 24 else 36
    record = {
        "id": product_id,
        "short_code": short_code,
        "name": name,
        "category": category,
        "description": description,
        "capture_mode": "turntable_video",
        "target_frames": clean_target,
        "canvas_size": settings.OUTPUT_CANVAS_SIZE,
        "status": "queued",
        "progress": 5,
        "stage": "extracting_frames",
        "share_url": f"/s/{short_code}",
        "viewer_url": f"/viewer/{product_id}",
        "hotspots": [],
    }
    created = create_product(record)
    queue_worker.enqueue_turntable_video_job(
        product_id=product_id,
        video_path=video_path,
        target_frames=clean_target,
        ai_mode=ai_mode,
    )
    return created


@app.post("/api/products/{product_id}/presigned-url")
def api_get_presigned_upload_url(
    product_id: str,
    filename: str = "capture.jpg",
    content_type: str = "image/jpeg",
):
    """FR-03: Generates a Presigned URL for direct Cloud Storage upload."""
    return storage_service.generate_presigned_upload(product_id, filename, content_type)


@app.post("/api/products/{product_id}/hotspots", response_model=ProductResponse)
def api_add_hotspot(product_id: str, req: HotspotCreateRequest):
    """FR-05: Adds an interactive Hotspot pin on a specific frame and updates index.json."""
    product = get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm.")

    hotspots = list(product.get("hotspots", []))
    new_hs = {
        "id": f"hs-{uuid.uuid4().hex[:8]}",
        "frame_index": req.frame_index,
        "x": round(req.x, 4),
        "y": round(req.y, 4),
        "title": req.title,
        "description": req.description,
        "tag_type": req.tag_type,
        "visible_range": req.visible_range,
    }
    hotspots.append(new_hs)
    updated = update_product(product_id, {"hotspots": hotspots})
    if updated and updated.get("status") == "completed":
        sync_index_json(updated)
    return updated


@app.put("/api/products/{product_id}/hotspots", response_model=ProductResponse)
def api_replace_hotspots(product_id: str, req: HotspotsBulkUpdateRequest):
    """FR-05: Replaces all hotspots for a product and syncs index.json."""
    product = get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm.")

    hs_dicts = [h.model_dump() for h in req.hotspots]
    updated = update_product(product_id, {"hotspots": hs_dicts})
    if updated and updated.get("status") == "completed":
        sync_index_json(updated)
    return updated


@app.delete("/api/products/{product_id}/hotspots/{hotspot_id}", response_model=ProductResponse)
def api_delete_hotspot(product_id: str, hotspot_id: str):
    product = get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm.")

    hotspots = [h for h in product.get("hotspots", []) if h.get("id") != hotspot_id]
    updated = update_product(product_id, {"hotspots": hotspots})
    if updated and updated.get("status") == "completed":
        sync_index_json(updated)
    return updated


@app.post("/api/products/{product_id}/export-mp4")
def api_export_mp4(product_id: str, req: VideoExportRequest):
    """
    FR-06: Renders a 9:16 (TikTok Shop / Shopee Video) or 1:1 (Square) MP4 showcase video.
    """
    product = get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm.")
    if product.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Sản phẩm đang được xử lý, vui lòng đợi hoàn tất.")

    ratio_key, url = export_product_mp4(
        product_record=product,
        aspect_ratio=req.aspect_ratio,
        loops=req.loops,
        fps=req.fps,
        bg_theme=req.bg_theme,
    )
    exports = dict(product.get("exports", {}))
    exports[ratio_key] = url
    updated = update_product(product_id, {"exports": exports})
    if updated:
        sync_index_json(updated)

    return {
        "product_id": product_id,
        "aspect_ratio": req.aspect_ratio,
        "export_key": ratio_key,
        "video_url": url,
        "product": updated,
    }


@app.delete("/api/products/{product_id}")
def api_delete_product(product_id: str):
    deleted = delete_product_record(product_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm.")
    storage_service.delete_product_files(product_id)
    shutil.rmtree(UPLOADS_STORAGE_DIR / product_id, ignore_errors=True)
    return {"deleted": True, "product_id": product_id}


def _render_viewer_html_with_og(product: Optional[dict], request: Request) -> HTMLResponse:
    viewer_file = WEB_VIEWER_DIR / "viewer.html"
    if not viewer_file.exists():
        return HTMLResponse("<h1>Web Viewer not found</h1>", status_code=404)

    html = viewer_file.read_text(encoding="utf-8")
    if product:
        base_url = str(request.base_url).rstrip("/")
        title = f"{product['name']} — Khung Xoay 360° Tương Tác"
        desc = product.get("description") or "Vuốt để xoay 360°, phóng to từng chi tiết sản phẩm."
        thumb = f"{base_url}{product.get('thumbnail_url') or ''}"
        html = (
            html.replace("__OG_TITLE__", title)
            .replace("__OG_DESCRIPTION__", desc)
            .replace("__OG_IMAGE__", thumb)
            .replace("__INITIAL_PRODUCT_ID__", product["id"])
        )
    else:
        html = (
            html.replace("__OG_TITLE__", "Pocket 3D Showcase — 360° Interactive Viewer")
            .replace("__OG_DESCRIPTION__", "Trình hiển thị sản phẩm 360° siêu nhẹ.")
            .replace("__OG_IMAGE__", "")
            .replace("__INITIAL_PRODUCT_ID__", "")
        )
    return HTMLResponse(content=html)


@app.get("/s/{short_code}", response_class=HTMLResponse)
def public_short_link_viewer(short_code: str, request: Request):
    """FR-05 & FR-06: Public short URL for sharing on Zalo, Facebook, Shopee, Website."""
    product = get_product_by_short_code(short_code)
    return _render_viewer_html_with_og(product, request)


@app.get("/viewer/{product_id}", response_class=HTMLResponse)
def public_product_viewer(product_id: str, request: Request):
    product = get_product(product_id) or get_product_by_short_code(product_id)
    return _render_viewer_html_with_og(product, request)


@app.get("/", response_class=HTMLResponse)
def studio_index():
    index_file = WEB_VIEWER_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return HTMLResponse("<h1>Pocket 3D Showcase API is running.</h1>")
