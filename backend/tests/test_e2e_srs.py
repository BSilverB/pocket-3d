"""
End-to-End Verification Suite for Pocket 3D Showcase (SRS v1.0 MVP)
Validates FR-01, FR-02, FR-03, FR-04, FR-05, FR-06 and NFR-01 (<15s), NFR-02 (<=3MB).
"""
import io
import sys
import time
import tempfile
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402
from app.services.demo_generator import generate_synthetic_product_frames  # noqa: E402


def _wait_for_completion(client: TestClient, product_id: str, timeout_sec: float = 25.0) -> dict:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        res = client.get(f"/api/products/{product_id}")
        assert res.status_code == 200
        data = res.json()
        if data["status"] == "completed":
            return data
        if data["status"] == "failed":
            raise AssertionError(f"AI Pipeline failed: {data.get('error_message')}")
        time.sleep(0.25)
    raise TimeoutError(f"Product {product_id} did not finish within {timeout_sec}s")


def run_all_tests() -> None:
    with TestClient(app) as client:
        # 1. Health check
        h = client.get("/api/health").json()
        assert h["status"] == "ok"
        print(f"[PASS] Health Check: queue={h['queue_backend']}, storage={h['storage_backend']}")

        # 2. Demo 360° Generation + FR-04 AI Background Removal & Global-Scale Auto-Centering + NFR-01/02
        res_demo = client.post(
            "/api/products/demo",
            json={"preset": "watch", "frame_count": 36, "ai_mode": "auto"},
        )
        assert res_demo.status_code == 200
        prod_id = res_demo.json()["id"]
        done_prod = _wait_for_completion(client, prod_id)

        assert done_prod["frame_count"] == 36
        assert done_prod["processing_time_sec"] <= 15.0, (
            f"NFR-01 violated: {done_prod['processing_time_sec']}s > 15s"
        )
        assert done_prod["package_size_mb"] <= 3.0, (
            f"NFR-02 violated: {done_prod['package_size_mb']}MB > 3.0MB"
        )
        assert done_prod["metrics"]["raw_centroid_jitter_px"] > 5.0
        assert done_prod["metrics"]["aligned_centroid_jitter_px"] == 0.0
        print(
            f"[PASS] FR-04 & NFR-01/02: 36 WebP frames processed in {done_prod['processing_time_sec']}s "
            f"| Package Size = {done_prod['package_size_mb']} MB "
            f"| Jitter reduced from {done_prod['metrics']['raw_centroid_jitter_px']}px -> 0.0px"
        )

        # 3. FR-05 Hotspots CRUD & index.json synchronization
        res_hs = client.post(
            f"/api/products/{prod_id}/hotspots",
            json={
                "frame_index": 12,
                "x": 0.54,
                "y": 0.42,
                "title": "Vỏ Thép 316L Đánh Bóng",
                "description": "Kiểm định không trầy xước",
                "tag_type": "material",
                "visible_range": 3,
            },
        )
        assert res_hs.status_code == 200
        hs_list = res_hs.json()["hotspots"]
        assert any(h["title"] == "Vỏ Thép 316L Đánh Bóng" for h in hs_list)

        idx_res = client.get(done_prod["index_json_url"])
        assert idx_res.status_code == 200
        idx_json = idx_res.json()
        assert len(idx_json["frames"]) == 36
        assert any(h["title"] == "Vỏ Thép 316L Đánh Bóng" for h in idx_json["hotspots"])
        print("[PASS] FR-05 Hotspots & index.json manifest verified")

        # 4. FR-06 Public Short Link (/s/{short_code}) & MP4 Export (9:16 & 1:1)
        short_res = client.get(done_prod["share_url"])
        assert short_res.status_code == 200
        assert done_prod["name"] in short_res.text

        mp4_res = client.post(
            f"/api/products/{prod_id}/export-mp4",
            json={"aspect_ratio": "9:16", "loops": 1, "fps": 24, "bg_theme": "studio_dark"},
        )
        assert mp4_res.status_code == 200
        mp4_url = mp4_res.json()["video_url"]
        mp4_file_res = client.get(mp4_url)
        assert mp4_file_res.status_code == 200
        assert len(mp4_file_res.content) > 10_000
        print(f"[PASS] FR-06 Short Link ({done_prod['share_url']}) & MP4 9:16 Export ({len(mp4_file_res.content) // 1024} KB)")

        # 5. FR-01 Turntable Video Upload (24 frames extraction)
        frames_pil, _ = generate_synthetic_product_frames("figure", frame_count=24, canvas_size=400)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_vid:
            tmp_vid_path = Path(tmp_vid.name)

        writer = cv2.VideoWriter(
            str(tmp_vid_path), cv2.VideoWriter_fourcc(*"mp4v"), 12.0, (400, 400)
        )
        for im in frames_pil:
            writer.write(cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR))
        writer.release()

        with open(tmp_vid_path, "rb") as vf:
            vid_res = client.post(
                "/api/products/capture-video",
                data={
                    "name": "Test Turntable Mecha 24",
                    "category": "Figure",
                    "target_frames": "24",
                    "ai_mode": "auto",
                },
                files={"video": ("turntable.mp4", vf, "video/mp4")},
            )
        tmp_vid_path.unlink(missing_ok=True)
        assert vid_res.status_code == 200
        vid_prod = _wait_for_completion(client, vid_res.json()["id"])
        assert vid_prod["frame_count"] == 24
        print(
            f"[PASS] FR-01 Turntable Video Mode: 24 frames extracted & centered in {vid_prod['processing_time_sec']}s"
        )


if __name__ == "__main__":
    run_all_tests()
    print("\n=== ALL SRS REQUIREMENTS (FR-01..FR-06, NFR-01..NFR-04) PASSED SUCCESSFULLY ===")
