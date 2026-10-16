/**
 * Pocket 3D Showcase — HTML5 Canvas 360° Sprite Spin Engine (FR-05, NFR-01, NFR-03)
 * Optimized for 60fps touch/mouse rotation, progressive WebP preloading (<2s initial load),
 * pinch/wheel Zoom & Pan, interactive Hotspots, and Before/After jitter comparison.
 */
export class SpinViewer360 {
  constructor(options) {
    this.canvas = options.canvas;
    this.ctx = this.canvas.getContext("2d");
    this.hotspotLayer = options.hotspotLayer;
    this.onFrameChange = options.onFrameChange || (() => {});
    this.onLoadProgress = options.onLoadProgress || (() => {});
    this.onHotspotSelect = options.onHotspotSelect || (() => {});
    this.onCanvasPinClick = options.onCanvasPinClick || null;

    this.frames = [];
    this.rawFrames = [];
    this.hotspots = [];
    this.frameCount = 0;
    this.currentFrame = 0;
    this.floatFrame = 0;

    // View state
    this.zoom = 1.0;
    this.panX = 0;
    this.panY = 0;
    this.autoSpin = false;
    this.autoSpinSpeed = 0.16; // frames per tick at 60fps
    this.viewMode = "processed"; // "processed" | "raw"
    this.pinPlacementMode = false;
    this.selectedHotspotId = null;

    // Interaction state
    this.isDragging = false;
    this.dragMode = "spin"; // "spin" | "pan"
    this.startX = 0;
    this.startY = 0;
    this.lastX = 0;
    this.lastY = 0;
    this.velocity = 0;
    this.dragMoved = false;
    this.targetAnimFrame = null;

    // Pinch zoom state
    this.activePointers = new Map();
    this.initialPinchDist = null;
    this.initialPinchZoom = 1.0;

    this._rafId = null;
    this._bindEvents();
    this._resizeObserver = new ResizeObserver(() => this.resize());
    this._resizeObserver.observe(this.canvas.parentElement || this.canvas);
    this.resize();
    this._startLoop();
  }

  resize() {
    const rect = this.canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.max(300, Math.floor(rect.width * dpr));
    const h = Math.max(300, Math.floor(rect.height * dpr));
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
    this.render();
  }

  async loadProduct(productData) {
    const urls = productData.frames || [];
    const rawUrls = productData.raw_frames || [];
    this.hotspots = productData.hotspots || [];
    this.frameCount = urls.length;
    this.frames = new Array(this.frameCount).fill(null);
    this.rawFrames = new Array(rawUrls.length).fill(null);
    this.currentFrame = 0;
    this.floatFrame = 0;
    this.zoom = 1.0;
    this.panX = 0;
    this.panY = 0;
    this.selectedHotspotId = null;

    if (this.frameCount === 0) {
      this.render();
      this.renderHotspots();
      return;
    }

    const t0 = performance.now();
    let loadedCount = 0;

    const loadSingle = (url, index, targetArray, highPriority = false) =>
      new Promise((resolve) => {
        const img = new Image();
        img.crossOrigin = "anonymous";
        if (highPriority && "fetchPriority" in img) {
          img.fetchPriority = "high";
        }
        img.onload = () => {
          targetArray[index] = img;
          if (targetArray === this.frames) {
            loadedCount++;
            this.onLoadProgress(loadedCount, this.frameCount, performance.now() - t0);
            if (index === this.currentFrame || loadedCount === 1) {
              this.render();
              this.renderHotspots();
            }
          }
          resolve(img);
        };
        img.onerror = () => resolve(null);
        img.src = url;
      });

    // Step 1: Load Frame 0 with high priority for instant LCP (<2s requirement NFR-01)
    await loadSingle(urls[0], 0, this.frames, true);

    // Step 2: Load cardinal quarter angles first so user can spin immediately
    const priorityIndices = [
      Math.floor(this.frameCount * 0.25),
      Math.floor(this.frameCount * 0.5),
      Math.floor(this.frameCount * 0.75),
    ].filter((i) => i > 0 && i < this.frameCount);

    await Promise.all(priorityIndices.map((idx) => loadSingle(urls[idx], idx, this.frames, false)));

    // Step 3: Load all remaining WebP frames in parallel
    const remaining = [];
    for (let i = 1; i < this.frameCount; i++) {
      if (!priorityIndices.includes(i)) {
        remaining.push(loadSingle(urls[i], i, this.frames, false));
      }
    }
    await Promise.all(remaining);

    // Step 4: Background preload raw frames for Before/After comparison toggle
    rawUrls.forEach((rUrl, idx) => {
      loadSingle(rUrl, idx, this.rawFrames, false);
    });

    this.render();
    this.renderHotspots();
  }

  setHotspots(hotspots) {
    this.hotspots = hotspots || [];
    this.renderHotspots();
  }

  setViewMode(mode) {
    this.viewMode = mode === "raw" ? "raw" : "processed";
    this.render();
  }

  setAutoSpin(enabled) {
    this.autoSpin = Boolean(enabled);
    if (this.autoSpin) {
      this.targetAnimFrame = null;
    }
  }

  setPinPlacementMode(enabled) {
    this.pinPlacementMode = Boolean(enabled);
    const container = this.canvas.parentElement;
    if (container) {
      container.classList.toggle("pin-cursor", this.pinPlacementMode);
    }
    if (this.pinPlacementMode) {
      this.autoSpin = false;
    }
  }

  setZoom(newZoom) {
    this.zoom = Math.max(1.0, Math.min(3.5, newZoom));
    if (this.zoom <= 1.02) {
      this.panX = 0;
      this.panY = 0;
    }
    this.render();
    this.renderHotspots();
  }

  setFrame(index) {
    if (this.frameCount <= 0) return;
    const norm = ((index % this.frameCount) + this.frameCount) % this.frameCount;
    this.currentFrame = Math.floor(norm);
    this.floatFrame = norm;
    this.onFrameChange(this.currentFrame, this.frameCount);
    this.render();
    this.renderHotspots();
  }

  rotateToFrame(targetIdx) {
    if (this.frameCount <= 0) return;
    this.autoSpin = false;
    this.velocity = 0;
    this.targetAnimFrame = ((targetIdx % this.frameCount) + this.frameCount) % this.frameCount;
  }

  _bindEvents() {
    const el = this.canvas.parentElement || this.canvas;

    el.addEventListener("pointerdown", (e) => {
      if (e.target.closest(".hotspot-pin") || e.target.closest(".viewer-hud-bottom") || e.target.closest(".viewer-hud-top") || e.target.closest(".hotspot-popover")) {
        return;
      }
      el.setPointerCapture(e.pointerId);
      this.activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY });

      if (this.activePointers.size === 2) {
        const pts = Array.from(this.activePointers.values());
        this.initialPinchDist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
        this.initialPinchZoom = this.zoom;
        this.isDragging = false;
        return;
      }

      this.isDragging = true;
      this.dragMoved = false;
      this.startX = e.clientX;
      this.startY = e.clientY;
      this.lastX = e.clientX;
      this.lastY = e.clientY;
      this.velocity = 0;
      this.targetAnimFrame = null;
      this.dragMode = e.shiftKey || e.button === 2 ? "pan" : "spin";
    });

    el.addEventListener("pointermove", (e) => {
      if (this.activePointers.has(e.pointerId)) {
        this.activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      }

      // Handle 2-finger pinch-to-zoom on mobile
      if (this.activePointers.size === 2 && this.initialPinchDist > 10) {
        const pts = Array.from(this.activePointers.values());
        const dist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
        const ratio = dist / this.initialPinchDist;
        this.setZoom(this.initialPinchZoom * ratio);
        return;
      }

      if (!this.isDragging || this.frameCount <= 0) return;

      const dx = e.clientX - this.lastX;
      const dy = e.clientY - this.lastY;
      if (Math.hypot(e.clientX - this.startX, e.clientY - this.startY) > 5) {
        this.dragMoved = true;
      }

      if (this.dragMode === "pan" && this.zoom > 1.05) {
        this.panX += dx;
        this.panY += dy;
        this.render();
        this.renderHotspots();
      } else {
        // Sensitivity: full 360 spin across ~380px horizontal drag
        const rect = this.canvas.getBoundingClientRect();
        const pxPerFrame = Math.max(6, rect.width / (this.frameCount * 1.15));
        const deltaFrames = -dx / pxPerFrame;
        this.floatFrame = ((this.floatFrame + deltaFrames) % this.frameCount + this.frameCount) % this.frameCount;
        const nextIdx = Math.floor(this.floatFrame);
        if (nextIdx !== this.currentFrame) {
          this.currentFrame = nextIdx;
          this.onFrameChange(this.currentFrame, this.frameCount);
        }
        this.velocity = deltaFrames * 0.65;
        this.render();
        this.renderHotspots();
      }

      this.lastX = e.clientX;
      this.lastY = e.clientY;
    });

    const endPointer = (e) => {
      this.activePointers.delete(e.pointerId);
      if (this.activePointers.size < 2) {
        this.initialPinchDist = null;
      }

      if (this.isDragging) {
        this.isDragging = false;
        // Check if it was a clean click in Pin Placement Mode
        if (!this.dragMoved && this.pinPlacementMode && this.onCanvasPinClick) {
          const rect = this.canvas.getBoundingClientRect();
          const clickX = (e.clientX - rect.left - rect.width / 2 - this.panX) / (rect.width * this.zoom) + 0.5;
          const clickY = (e.clientY - rect.top - rect.height / 2 - this.panY) / (rect.height * this.zoom) + 0.5;
          const normX = Math.max(0.05, Math.min(0.95, clickX));
          const normY = Math.max(0.05, Math.min(0.95, clickY));
          this.onCanvasPinClick({
            frame_index: this.currentFrame,
            x: Number(normX.toFixed(4)),
            y: Number(normY.toFixed(4)),
          });
        }
      }
    };

    el.addEventListener("pointerup", endPointer);
    el.addEventListener("pointercancel", endPointer);

    // Wheel Zoom
    el.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        const factor = e.deltaY < 0 ? 1.12 : 0.89;
        this.setZoom(this.zoom * factor);
      },
      { passive: false }
    );
  }

  _startLoop() {
    const tick = () => {
      if (this.frameCount > 0 && !this.isDragging) {
        if (this.targetAnimFrame !== null) {
          // Shortest angular path to target frame
          let diff = this.targetAnimFrame - this.floatFrame;
          if (diff > this.frameCount / 2) diff -= this.frameCount;
          if (diff < -this.frameCount / 2) diff += this.frameCount;

          if (Math.abs(diff) < 0.25) {
            this.setFrame(this.targetAnimFrame);
            this.targetAnimFrame = null;
          } else {
            this.floatFrame =
              ((this.floatFrame + Math.sign(diff) * Math.max(0.22, Math.abs(diff) * 0.18)) %
                this.frameCount +
                this.frameCount) %
              this.frameCount;
            this.currentFrame = Math.floor(this.floatFrame);
            this.onFrameChange(this.currentFrame, this.frameCount);
            this.render();
            this.renderHotspots();
          }
        } else if (this.autoSpin) {
          this.floatFrame = (this.floatFrame + this.autoSpinSpeed) % this.frameCount;
          const nextIdx = Math.floor(this.floatFrame);
          if (nextIdx !== this.currentFrame) {
            this.currentFrame = nextIdx;
            this.onFrameChange(this.currentFrame, this.frameCount);
            this.render();
            this.renderHotspots();
          }
        } else if (Math.abs(this.velocity) > 0.015) {
          this.floatFrame =
            ((this.floatFrame + this.velocity) % this.frameCount + this.frameCount) %
            this.frameCount;
          this.velocity *= 0.91; // Smooth inertia damping
          const nextIdx = Math.floor(this.floatFrame);
          if (nextIdx !== this.currentFrame) {
            this.currentFrame = nextIdx;
            this.onFrameChange(this.currentFrame, this.frameCount);
          }
          this.render();
          this.renderHotspots();
        }
      }
      this._rafId = requestAnimationFrame(tick);
    };
    this._rafId = requestAnimationFrame(tick);
  }

  _getBestAvailableImage(index) {
    const sourceArr =
      this.viewMode === "raw" && this.rawFrames.some(Boolean) ? this.rawFrames : this.frames;
    if (sourceArr[index]) return sourceArr[index];
    // Find nearest loaded frame while streaming
    for (let offset = 1; offset < this.frameCount; offset++) {
      const prev = (index - offset + this.frameCount) % this.frameCount;
      if (sourceArr[prev]) return sourceArr[prev];
      const next = (index + offset) % this.frameCount;
      if (sourceArr[next]) return sourceArr[next];
    }
    return null;
  }

  render() {
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;
    ctx.clearRect(0, 0, w, h);

    // Subtle studio floor shadow ellipse when viewing processed transparent WebP
    if (this.viewMode === "processed") {
      ctx.save();
      ctx.translate(w / 2 + this.panX, h * 0.84 + this.panY);
      ctx.scale(this.zoom, this.zoom * 0.22);
      const grad = ctx.createRadialGradient(0, 0, w * 0.02, 0, 0, w * 0.34);
      grad.addColorStop(0, "rgba(0, 0, 0, 0.38)");
      grad.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(0, 0, w * 0.34, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    const img = this._getBestAvailableImage(this.currentFrame);
    if (!img) return;

    const dpr = this.canvas.width / Math.max(1, this.canvas.getBoundingClientRect().width);
    ctx.save();
    ctx.translate(w / 2 + this.panX * dpr, h / 2 + this.panY * dpr);
    ctx.scale(this.zoom, this.zoom);

    const drawSize = Math.min(w, h);
    ctx.drawImage(img, -drawSize / 2, -drawSize / 2, drawSize, drawSize);
    ctx.restore();
  }

  renderHotspots() {
    if (!this.hotspotLayer) return;
    this.hotspotLayer.innerHTML = "";
    if (!this.hotspots || this.hotspots.length === 0 || this.frameCount <= 0) return;

    const rect = this.canvas.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;

    this.hotspots.forEach((hs, idx) => {
      const range = hs.visible_range ?? 3;
      let dist = Math.abs(this.currentFrame - hs.frame_index);
      dist = Math.min(dist, this.frameCount - dist);

      // Show pin if within visible frame range
      if (dist <= range) {
        const pin = document.createElement("button");
        pin.type = "button";
        pin.className = `hotspot-pin type-${hs.tag_type || "detail"}`;
        pin.textContent = String(idx + 1);
        pin.title = hs.title;

        // Project normalized (x, y) through zoom & pan
        const screenX = w / 2 + this.panX + (hs.x - 0.5) * w * this.zoom;
        const screenY = h / 2 + this.panY + (hs.y - 0.5) * h * this.zoom;
        pin.style.left = `${screenX}px`;
        pin.style.top = `${screenY}px`;
        pin.style.opacity = dist === 0 ? "1" : "0.78";

        pin.addEventListener("click", (e) => {
          e.stopPropagation();
          this.selectedHotspotId = hs.id;
          this.rotateToFrame(hs.frame_index);
          this.onHotspotSelect(hs, idx);
        });

        this.hotspotLayer.appendChild(pin);
      }
    });
  }
}
