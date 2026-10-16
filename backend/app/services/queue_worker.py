import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Any
from PIL import Image

from ..config import settings
from ..database import get_product, update_product
from .ai_pipeline import extract_frames_from_video, run_full_ai_pipeline


class QueueWorkerManager:
    """
    FR-03 Ingestion & Queue Worker:
    Supports hybrid execution:
    - 'local': Asynchronous ThreadPoolExecutor worker inside FastAPI process (zero external setup required)
    - 'redis': Pushes job payload into Redis Queue (`REDIS_URL`) with automatic fallback to local executor
               if Redis server is unreachable.
    """

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pocket3d_worker")
        self._redis = None
        if settings.QUEUE_BACKEND.lower() == "redis":
            try:
                import redis
                client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1.5)
                client.ping()
                self._redis = client
            except Exception:
                self._redis = None

    @property
    def active_mode(self) -> str:
        return "redis" if self._redis is not None else "local_async_pool"

    def enqueue_image_batch_job(
        self,
        product_id: str,
        image_paths: List[Path],
        ai_mode: str = "auto",
    ) -> str:
        if self._redis is not None:
            payload = {
                "job_type": "image_batch",
                "product_id": product_id,
                "image_paths": [str(p) for p in image_paths],
                "ai_mode": ai_mode,
            }
            self._redis.rpush(settings.REDIS_QUEUE_NAME, json.dumps(payload))

        self._executor.submit(self._execute_image_batch, product_id, image_paths, ai_mode)
        return self.active_mode

    def enqueue_turntable_video_job(
        self,
        product_id: str,
        video_path: Path,
        target_frames: int = 36,
        ai_mode: str = "auto",
    ) -> str:
        if self._redis is not None:
            payload = {
                "job_type": "turntable_video",
                "product_id": product_id,
                "video_path": str(video_path),
                "target_frames": target_frames,
                "ai_mode": ai_mode,
            }
            self._redis.rpush(settings.REDIS_QUEUE_NAME, json.dumps(payload))

        self._executor.submit(
            self._execute_turntable_video, product_id, video_path, target_frames, ai_mode
        )
        return self.active_mode

    def enqueue_pil_frames_job(
        self,
        product_id: str,
        frames: List[Image.Image],
        ai_mode: str = "auto",
    ) -> str:
        self._executor.submit(self._execute_pil_frames, product_id, frames, ai_mode)
        return self.active_mode

    def _make_progress_updater(self, product_id: str):
        def _cb(progress: int, stage: str) -> None:
            update_product(
                product_id,
                {
                    "status": "completed" if progress >= 100 else "processing",
                    "progress": progress,
                    "stage": stage,
                },
            )

        return _cb

    def _execute_image_batch(
        self,
        product_id: str,
        image_paths: List[Path],
        ai_mode: str,
    ) -> None:
        try:
            update_product(product_id, {"status": "processing", "progress": 5, "stage": "loading_images"})
            pil_frames: List[Image.Image] = []
            for p in image_paths:
                with Image.open(p) as im:
                    pil_frames.append(im.copy())

            self._run_pipeline_and_save(product_id, pil_frames, ai_mode)
        except Exception as exc:
            traceback.print_exc()
            update_product(
                product_id,
                {
                    "status": "failed",
                    "stage": "failed",
                    "error_message": str(exc),
                },
            )

    def _execute_turntable_video(
        self,
        product_id: str,
        video_path: Path,
        target_frames: int,
        ai_mode: str,
    ) -> None:
        try:
            update_product(
                product_id,
                {"status": "processing", "progress": 8, "stage": "extracting_frames"},
            )
            pil_frames = extract_frames_from_video(video_path, target_frames=target_frames)
            self._run_pipeline_and_save(product_id, pil_frames, ai_mode)
        except Exception as exc:
            traceback.print_exc()
            update_product(
                product_id,
                {
                    "status": "failed",
                    "stage": "failed",
                    "error_message": str(exc),
                },
            )

    def _execute_pil_frames(
        self,
        product_id: str,
        pil_frames: List[Image.Image],
        ai_mode: str,
    ) -> None:
        try:
            update_product(product_id, {"status": "processing", "progress": 10, "stage": "removing_background"})
            self._run_pipeline_and_save(product_id, pil_frames, ai_mode)
        except Exception as exc:
            traceback.print_exc()
            update_product(
                product_id,
                {
                    "status": "failed",
                    "stage": "failed",
                    "error_message": str(exc),
                },
            )

    def _run_pipeline_and_save(
        self,
        product_id: str,
        pil_frames: List[Image.Image],
        ai_mode: str,
    ) -> None:
        product_meta = get_product(product_id)
        if not product_meta:
            return

        result = run_full_ai_pipeline(
            product_id=product_id,
            input_frames=pil_frames,
            product_meta=product_meta,
            ai_mode=ai_mode,
            progress_callback=self._make_progress_updater(product_id),
        )
        update_product(
            product_id,
            {
                "status": "completed",
                "progress": 100,
                "stage": "completed",
                **result,
            },
        )


queue_worker = QueueWorkerManager()
