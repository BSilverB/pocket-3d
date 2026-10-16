import math
from typing import Dict, List, Tuple, Any
import cv2
import numpy as np
from PIL import Image


DEMO_PRESETS: Dict[str, Dict[str, Any]] = {
    "sneaker": {
        "name": "Cyber Air Max Pro — Limited Edition",
        "category": "Sneakers / Giày Thể Thao",
        "description": "Giày sneaker phiên bản giới hạn đế Air Carbon, da Microfiber cao cấp kết hợp lưới thoáng khí 3D.",
        "default_hotspots": [
            {
                "id": "hs-sneaker-1",
                "frame_index": 0,
                "x": 0.62,
                "y": 0.56,
                "title": "Mũi giày Da Microfiber & Lưới BreathMesh",
                "description": "Chất liệu da tổng hợp chống nhăn kết hợp lỗ thoáng khí cắt laser độ bền cao.",
                "tag_type": "material",
                "visible_range": 3,
            },
            {
                "id": "hs-sneaker-2",
                "frame_index": 9,
                "x": 0.48,
                "y": 0.68,
                "title": "Đế đệm Nitro-Air & Thanh Carbon",
                "description": "Độ dày đế 4.2cm, đàn hồi 85%, chống trượt chuẩn marathon.",
                "tag_type": "dimension",
                "visible_range": 4,
            },
            {
                "id": "hs-sneaker-3",
                "frame_index": 18,
                "x": 0.34,
                "y": 0.45,
                "title": "Gót phản quang 3M & Tem chính hãng",
                "description": "Tình trạng 99% Likenew: Vết xước cực nhẹ 2mm ở viền đế sau bên trái (hàng sưu tầm).",
                "tag_type": "defect",
                "visible_range": 3,
            },
        ],
    },
    "watch": {
        "name": "Chronos Royal Tourbillon 42mm",
        "category": "Luxury Watch / Đồng Hồ Cơ",
        "description": "Đồng hồ cơ lộ máy Skeleton Automatic mặt kính Sapphire nguyên khối, vỏ thép 316L mạ PVD Vàng Hồng.",
        "default_hotspots": [
            {
                "id": "hs-watch-1",
                "frame_index": 0,
                "x": 0.50,
                "y": 0.48,
                "title": "Mặt kính Sapphire & Lồng Tourbillon",
                "description": "Kính Sapphire chống trầy hai mặt phủ AR xanh, bộ máy cơ tự động 28,800 vph.",
                "tag_type": "material",
                "visible_range": 4,
            },
            {
                "id": "hs-watch-2",
                "frame_index": 8,
                "x": 0.63,
                "y": 0.49,
                "title": "Núm vặn Crown Khía Kim Cương",
                "description": "Đường kính vỏ 42mm, độ dày 11.4mm, chống nước 10 ATM (100m).",
                "tag_type": "dimension",
                "visible_range": 3,
            },
            {
                "id": "hs-watch-3",
                "frame_index": 18,
                "x": 0.50,
                "y": 0.52,
                "title": "Đáy lộ cơ Caseback & Số Serial",
                "description": "Khắc laser số thứ tự Limited #088/500, quả văng mạ vàng hồng 18K.",
                "tag_type": "detail",
                "visible_range": 4,
            },
        ],
    },
    "figure": {
        "name": "Mecha Valkyrie RX-09 Collector Figure",
        "category": "Figure / Mô Hình Sưu Tầm",
        "description": "Mô hình Mecha tỷ lệ 1/72 khung xương hợp kim Die-cast sơn tĩnh điện Metallic kèm giáp năng lượng.",
        "default_hotspots": [
            {
                "id": "hs-figure-1",
                "frame_index": 0,
                "x": 0.50,
                "y": 0.30,
                "title": "Đầu Mecha Antenna V-Fin Mạ Chrome",
                "description": "Mắt phủ sơn huỳnh quang UV LED, sừng V-Fin sắc nét không lỗi sơn.",
                "tag_type": "detail",
                "visible_range": 3,
            },
            {
                "id": "hs-figure-2",
                "frame_index": 10,
                "x": 0.62,
                "y": 0.46,
                "title": "Giáp Vai Khiên Năng Lượng Plasma",
                "description": "Chiều cao tổng thể 26.5cm, khớp hợp kim Die-cast xoay 180 độ.",
                "tag_type": "dimension",
                "visible_range": 4,
            },
            {
                "id": "hs-figure-3",
                "frame_index": 22,
                "x": 0.45,
                "y": 0.42,
                "title": "Bộ Đẩy Thruster Backpack",
                "description": "Hàng Fullbox 98%: Hơi bạc màu nhẹ ở mép ống xả phải do trưng bày tủ kính.",
                "tag_type": "defect",
                "visible_range": 3,
            },
        ],
    },
}


def _project_3d_points(
    pts: np.ndarray,
    yaw_rad: float,
    pitch_rad: float = 0.22,
    center_xy: Tuple[float, float] = (320.0, 320.0),
    focal: float = 520.0,
    cam_dist: float = 4.2,
) -> Tuple[np.ndarray, np.ndarray]:
    """Projects 3D points (N, 3) into 2D screen coordinates (N, 2) and depth Z."""
    cy, sy = math.cos(yaw_rad), math.sin(yaw_rad)
    cp, sp = math.cos(pitch_rad), math.sin(pitch_rad)

    # Rotate around Y axis (yaw)
    x1 = pts[:, 0] * cy + pts[:, 2] * sy
    y1 = pts[:, 1]
    z1 = -pts[:, 0] * sy + pts[:, 2] * cy

    # Rotate around X axis (pitch)
    x2 = x1
    y2 = y1 * cp - z1 * sp
    z2 = y1 * sp + z1 * cp

    z_cam = cam_dist - z2
    z_cam = np.maximum(z_cam, 0.5)

    u = center_xy[0] + (x2 * focal) / z_cam
    v = center_xy[1] - (y2 * focal) / z_cam
    return np.stack([u, v], axis=1), z2


def _build_sneaker_voxels() -> List[Tuple[np.ndarray, Tuple[int, int, int], float]]:
    """Builds a stylized 3D sneaker model composed of shaded 3D primitives (x: length, y: height, z: width)."""
    parts = []
    # 1. Midsole (White/Light Cyan aerodynamic wedge)
    for x in np.linspace(-1.25, 1.30, 28):
        half_w = 0.42 - 0.08 * (x - 0.1) ** 2
        if x > 0.8:
            half_w *= max(0.25, 1.0 - ((x - 0.8) / 0.65) ** 1.6)
        for z in np.linspace(-half_w, half_w, 10):
            # Outsole bottom tread (Electric Coral / Neon Orange)
            parts.append((np.array([x, -0.52, z]), (245, 78, 52), 18.0))
            # Midsole cushion (Clean Pearl Grey-Blue)
            is_air_window = (-0.95 <= x <= -0.15) and (abs(z) > half_w * 0.72)
            col = (56, 215, 245) if is_air_window else (232, 236, 245)
            parts.append((np.array([x, -0.38, z]), col, 20.0))

    # 2. Upper body (Deep Cobalt / Cyber Indigo with Neon Lime & Crimson accents)
    for x in np.linspace(-1.18, 1.18, 25):
        # Height profile of a sneaker: high heel/collar at x in [-1.1, -0.3], sloping down to toe box at x > 0.3
        if x < -0.25:
            top_y = 0.48 - 0.25 * abs(x + 0.65)
        else:
            top_y = 0.42 * math.exp(-0.95 * (x + 0.25)) - 0.12

        half_w = 0.39 - 0.07 * (x - 0.05) ** 2
        if x > 0.75:
            half_w *= max(0.2, 1.0 - ((x - 0.75) / 0.55) ** 1.5)

        for y in np.linspace(-0.24, top_y, 7):
            # Collar opening hole near (-0.65, top)
            is_collar_opening = (-0.92 <= x <= -0.32) and (y > 0.22)
            for z in np.linspace(-half_w, half_w, 8):
                if is_collar_opening and abs(z) < half_w * 0.62:
                    continue
                # Color zones
                is_swoosh = (abs(z) > half_w * 0.75) and abs(y - (0.12 * x + 0.04)) < 0.085 and (-0.75 <= x <= 0.45)
                is_laces = (-0.28 <= x <= 0.42) and (y > top_y - 0.11) and (abs(z) < half_w * 0.55)
                is_heel_tab = (x < -0.95) and (y > 0.05)
                if is_swoosh:
                    c = (45, 245, 155)  # Neon Mint Swoosh
                elif is_heel_tab:
                    c = (255, 85, 65)  # Reflective Crimson Heel
                elif is_laces:
                    c = (240, 244, 252) if int((x + 0.3) * 14) % 2 == 0 else (38, 45, 72)
                elif x > 0.55:
                    c = (48, 92, 215)  # Royal Toe Box
                else:
                    c = (32, 54, 135)  # Deep Navy Quarter Panel
                parts.append((np.array([x, y, z]), c, 19.0))

    return parts


def _build_watch_voxels() -> List[Tuple[np.ndarray, Tuple[int, int, int], float]]:
    """Builds a stylized 3D Luxury Tourbillon Chronograph Watch."""
    parts = []
    # 1. Watch Case & Bezel (Rose Gold PVD & Sapphire Dial)
    for r in np.linspace(0.0, 0.88, 16):
        steps = max(12, int(r * 42))
        for a in np.linspace(0, 2 * math.pi, steps, endpoint=False):
            x = r * math.cos(a)
            y = r * math.sin(a)
            # Case back (z = -0.18) to front bezel (z = +0.18)
            for z in [-0.16, 0.0, 0.16]:
                if r > 0.72:
                    # Rose Gold Metallic Bezel
                    c = (228, 168, 118)
                elif z > 0:
                    # Deep Emerald/Midnight Blue Dial with Tourbillon cage at bottom (y < -0.2)
                    in_tourbillon = math.hypot(x, y + 0.34) < 0.22
                    is_hour_hand = abs(a - 0.85) < 0.12 and r < 0.48
                    is_min_hand = abs(a - 2.35) < 0.08 and r < 0.64
                    if in_tourbillon:
                        c = (242, 198, 92)  # Gold Tourbillon Bridge
                    elif is_hour_hand or is_min_hand:
                        c = (245, 232, 210)
                    else:
                        c = (24, 52, 92)
                else:
                    # Exhibition caseback
                    c = (195, 145, 102) if r > 0.45 else (95, 115, 145)
                parts.append((np.array([x, y, z]), c, 17.0))

    # Crown on right side (x = 0.96, y = 0)
    for z in np.linspace(-0.08, 0.08, 3):
        parts.append((np.array([0.96, 0.0, z]), (245, 188, 125), 20.0))
        parts.append((np.array([0.90, 0.28, z]), (215, 160, 110), 15.0))
        parts.append((np.array([0.90, -0.28, z]), (215, 160, 110), 15.0))

    # 2. Curved Strap (Alligator Brown/Burgundy Leather curving behind in Z)
    for theta in np.linspace(0.55, 2.55, 22):
        # Upper and lower strap arcs
        for sign_y in [1.0, -1.0]:
            sy = sign_y * (0.72 + 0.52 * math.sin(theta * 0.75))
            sz = -0.15 - 0.85 * (1.0 - math.cos((theta - 0.55) * 0.85))
            for sx in np.linspace(-0.34, 0.34, 7):
                is_stitch = abs(sx) > 0.26
                c = (218, 182, 138) if is_stitch else (108, 56, 42)
                parts.append((np.array([sx, sy, sz]), c, 16.0))

    return parts


def _build_figure_voxels() -> List[Tuple[np.ndarray, Tuple[int, int, int], float]]:
    """Builds a stylized 3D Collector Mecha Figure."""
    parts = []
    # Head & V-Fin Crest
    for y in np.linspace(0.68, 1.02, 6):
        for x in np.linspace(-0.22, 0.22, 5):
            for z in np.linspace(-0.20, 0.22, 5):
                is_visor = (z > 0.12) and (0.76 <= y <= 0.86) and (abs(x) < 0.16)
                c = (40, 248, 165) if is_visor else (225, 232, 245)
                parts.append((np.array([x, y, z]), c, 16.0))
    # Gold V-Fin Antenna
    for t in np.linspace(0.05, 0.45, 7):
        parts.append((np.array([t, 0.95 + t * 0.55, 0.22]), (248, 202, 58), 14.0))
        parts.append((np.array([-t, 0.95 + t * 0.55, 0.22]), (248, 202, 58), 14.0))

    # Torso Armor (Cobalt Blue + Crimson Chest Core)
    for y in np.linspace(-0.10, 0.64, 11):
        for x in np.linspace(-0.42, 0.42, 9):
            for z in np.linspace(-0.26, 0.28, 6):
                is_core = (z > 0.18) and (0.18 <= y <= 0.42) and (abs(x) < 0.18)
                is_vent = (z > 0.18) and (0.22 <= y <= 0.38) and (0.18 <= abs(x) <= 0.34)
                if is_core:
                    c = (245, 62, 72)
                elif is_vent:
                    c = (248, 202, 58)
                else:
                    c = (38, 82, 205)
                parts.append((np.array([x, y, z]), c, 18.0))

    # Shoulders & Arms + Energy Shield on Right Arm
    for side in [-1.0, 1.0]:
        for y in np.linspace(0.32, 0.68, 6):
            for x in np.linspace(0.46, 0.78, 5):
                parts.append((np.array([side * x, y, 0.0]), (235, 240, 250), 19.0))
        # Forearms
        for y in np.linspace(-0.18, 0.30, 7):
            parts.append((np.array([side * 0.62, y, 0.08]), (195, 55, 65), 18.0))

    # Plasma Shield on Left/Right side
    for y in np.linspace(-0.35, 0.55, 11):
        for z in np.linspace(-0.28, 0.32, 6):
            c = (52, 215, 248) if abs(y) < 0.25 and abs(z) < 0.16 else (238, 72, 68)
            parts.append((np.array([0.84, y, z]), c, 17.0))

    # Thruster Backpack (z < -0.28)
    for y in np.linspace(0.10, 0.58, 7):
        for x in [-0.22, 0.22]:
            parts.append((np.array([x, y, -0.38]), (92, 104, 128), 19.0))

    # Legs
    for side in [-1.0, 1.0]:
        for y in np.linspace(-1.05, -0.12, 13):
            for x in np.linspace(0.14, 0.36, 4):
                for z in np.linspace(-0.16, 0.18, 4):
                    c = (228, 65, 65) if y < -0.82 else (228, 234, 246)
                    parts.append((np.array([side * x, y, z]), c, 18.0))

    return parts


def generate_synthetic_product_frames(
    preset: str = "sneaker",
    frame_count: int = 36,
    canvas_size: int = 640,
) -> Tuple[List[Image.Image], Dict[str, Any]]:
    """
    Renders `frame_count` synthetic 360-degree raw product photographs with:
    1. A contrasting studio background (warm beige/cream studio backdrop) so AI Background Removal
       is genuinely tested.
    2. Intentional camera hand-shake / turntable eccentricity jitter (+/- 24px X/Y offset per frame)
       so Global-Scale Auto-Centering visibly stabilizes 100% of the wobble.
    """
    preset_key = preset if preset in DEMO_PRESETS else "sneaker"
    if preset_key == "watch":
        voxels = _build_watch_voxels()
    elif preset_key == "figure":
        voxels = _build_figure_voxels()
    else:
        voxels = _build_sneaker_voxels()

    pts = np.array([v[0] for v in voxels], dtype=np.float32)
    base_colors = np.array([v[1] for v in voxels], dtype=np.float32)
    radii = np.array([v[2] for v in voxels], dtype=np.float32)

    rng = np.random.default_rng(seed=42)
    frames: List[Image.Image] = []

    # Pre-build a realistic warm studio backdrop (beige/warm gray gradient) so background remover
    # segments the colorful 3D product cleanly
    yy, xx = np.mgrid[0:canvas_size, 0:canvas_size].astype(np.float32)
    radial = np.hypot(xx - canvas_size * 0.5, yy - canvas_size * 0.5) / (canvas_size * 0.75)
    bg_r = np.clip(244 - 16 * radial, 215, 250).astype(np.uint8)
    bg_g = np.clip(238 - 18 * radial, 208, 245).astype(np.uint8)
    bg_b = np.clip(225 - 20 * radial, 195, 235).astype(np.uint8)
    studio_backdrop = np.dstack([bg_r, bg_g, bg_b])

    for idx in range(frame_count):
        yaw = (2.0 * math.pi * idx) / frame_count

        # Simulate realistic camera hand-shake / off-center turntable wobble (FR-04 test case)
        jitter_x = float(22.0 * math.sin(yaw * 2.0 + 0.4) + rng.uniform(-7.0, 7.0))
        jitter_y = float(16.0 * math.cos(yaw * 3.0 - 0.2) + rng.uniform(-6.0, 6.0))
        center_xy = (canvas_size * 0.5 + jitter_x, canvas_size * 0.52 + jitter_y)

        proj_uv, depth_z = _project_3d_points(
            pts,
            yaw_rad=yaw,
            pitch_rad=0.24,
            center_xy=center_xy,
            focal=canvas_size * 0.82,
            cam_dist=4.1,
        )

        # Sort back-to-front (Painter's algorithm)
        order = np.argsort(depth_z)
        img = studio_backdrop.copy()

        # Directional lighting based on depth & vertical coordinate
        shade = np.clip(0.82 + 0.22 * (depth_z / 1.4) + 0.12 * pts[:, 1], 0.55, 1.22)

        for i in order:
            u, v = int(round(proj_uv[i, 0])), int(round(proj_uv[i, 1]))
            if not (0 <= u < canvas_size and 0 <= v < canvas_size):
                continue
            r_px = max(3, int(round(radii[i] * (canvas_size / 640.0))))
            col = np.clip(base_colors[i] * shade[i], 0, 255).astype(int)
            color_tuple = (int(col[0]), int(col[1]), int(col[2]))
            cv2.circle(img, (u, v), r_px, color_tuple, thickness=-1, lineType=cv2.LINE_AA)
            # Subtle specular highlight on top-left of sphere primitive
            hi_tuple = (
                min(255, int(col[0] + 28)),
                min(255, int(col[1] + 28)),
                min(255, int(col[2] + 28)),
            )
            cv2.circle(
                img,
                (u - max(1, r_px // 3), v - max(1, r_px // 3)),
                max(1, r_px // 3),
                hi_tuple,
                thickness=-1,
                lineType=cv2.LINE_AA,
            )

        frames.append(Image.fromarray(img, mode="RGB"))

    return frames, DEMO_PRESETS[preset_key]
