from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class HotspotItem(BaseModel):
    id: str
    frame_index: int = Field(..., ge=0, description="Zero-based index of the frame where hotspot is pinned")
    x: float = Field(..., ge=0.0, le=1.0, description="Normalized X coordinate (0.0 to 1.0) on canvas")
    y: float = Field(..., ge=0.0, le=1.0, description="Normalized Y coordinate (0.0 to 1.0) on canvas")
    title: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    tag_type: str = Field(default="detail", description="detail | material | dimension | defect")
    visible_range: int = Field(default=2, ge=0, le=10, description="Number of neighboring frames +/- where pin remains visible")


class HotspotCreateRequest(BaseModel):
    frame_index: int = Field(..., ge=0)
    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)
    title: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    tag_type: str = Field(default="detail")
    visible_range: int = Field(default=2, ge=0, le=10)


class HotspotsBulkUpdateRequest(BaseModel):
    hotspots: List[HotspotItem]


class DemoGenerateRequest(BaseModel):
    preset: str = Field(
        default="sneaker",
        description="Preset 3D object to synthesize: 'sneaker' | 'watch' | 'figure'",
    )
    frame_count: int = Field(default=36, description="24 or 36 angles")
    name: Optional[str] = None
    category: Optional[str] = None
    ai_mode: str = Field(default="auto", description="'auto' | 'rembg' | 'studio_seg'")


class VideoExportRequest(BaseModel):
    aspect_ratio: str = Field(default="9:16", description="'9:16' (TikTok/Shopee Video) or '1:1' (Square)")
    loops: int = Field(default=2, ge=1, le=5)
    fps: int = Field(default=24, ge=12, le=60)
    bg_theme: str = Field(default="studio_dark", description="'studio_dark' | 'studio_light' | 'warm_sand'")


class ProductResponse(BaseModel):
    id: str
    short_code: str
    name: str
    category: str
    description: str
    capture_mode: str
    target_frames: int
    frame_count: int
    canvas_size: int
    status: str
    progress: int
    stage: str
    error_message: Optional[str] = None
    processing_time_sec: float
    package_size_mb: float
    ai_engine_used: str
    thumbnail_url: Optional[str] = None
    raw_preview_url: Optional[str] = None
    index_json_url: Optional[str] = None
    share_url: str
    viewer_url: str
    frames: List[str] = []
    raw_frames: List[str] = []
    hotspots: List[HotspotItem] = []
    exports: Dict[str, str] = {}
    metrics: Dict[str, Any] = {}
    created_at: str
    updated_at: str
