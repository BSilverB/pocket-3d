import { SpinViewer360 } from "./spin-viewer.js";

// Mandatory fallback for browsers without native <dialog closedby="any"> support (modern-web-guidance: light-dismiss-a-dialog)
function setupDialogLightDismissFallbacks() {
  document.querySelectorAll("dialog").forEach((dialog) => {
    if (!("closedBy" in HTMLDialogElement.prototype)) {
      dialog.addEventListener("click", (event) => {
        if (event.target !== dialog) return;
        const rect = dialog.getBoundingClientRect();
        const isDialogContent =
          rect.top <= event.clientY &&
          event.clientY <= rect.top + rect.height &&
          rect.left <= event.clientX &&
          event.clientX <= rect.left + rect.width;
        if (isDialogContent) return;
        dialog.close();
      });
    }
  });

  document.querySelectorAll("[data-close-dialog]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-close-dialog");
      const dlg = document.getElementById(targetId);
      if (dlg) dlg.close();
    });
  });
}

class Pocket3DStudioApp {
  constructor() {
    this.products = [];
    this.activeProduct = null;
    this.pendingPinCoord = null;
    this.pollTimer = null;

    this.viewer = new SpinViewer360({
      canvas: document.getElementById("spinCanvas"),
      hotspotLayer: document.getElementById("hotspotLayer"),
      onFrameChange: (frameIdx, total) => this.handleFrameChange(frameIdx, total),
      onLoadProgress: (loaded, total, ms) => this.handleLoadProgress(loaded, total, ms),
      onHotspotSelect: (hs) => this.showHotspotPopover(hs),
      onCanvasPinClick: (coords) => this.openCreateHotspotModal(coords),
    });

    this.bindUI();
    this.init();
  }

  async init() {
    setupDialogLightDismissFallbacks();
    await this.checkHealth();
    await this.loadProducts(true);
  }

  async checkHealth() {
    try {
      const res = await fetch("/api/health");
      const data = await res.json();
      const textEl = document.getElementById("healthText");
      if (textEl) {
        textEl.textContent = `Queue: ${data.queue_backend} • Storage: ${data.storage_backend.toUpperCase()}`;
      }
    } catch {
      // ignore
    }
  }

  async loadProducts(selectFirst = false) {
    const res = await fetch("/api/products");
    this.products = await res.json();
    document.getElementById("productCount").textContent = String(this.products.length);
    this.renderProductList();

    if (selectFirst && this.products.length > 0 && !this.activeProduct) {
      await this.selectProduct(this.products[0].id);
    } else if (this.activeProduct) {
      const updated = this.products.find((p) => p.id === this.activeProduct.id);
      if (updated) {
        const wasProcessing = this.activeProduct.status !== "completed";
        this.activeProduct = updated;
        this.updateRightSidebar(updated);
        if (wasProcessing && updated.status === "completed") {
          await this.viewer.loadProduct(updated);
        }
      }
    }

    // Poll while any product is still processing
    const anyProcessing = this.products.some(
      (p) => p.status === "queued" || p.status === "processing"
    );
    clearTimeout(this.pollTimer);
    if (anyProcessing) {
      this.pollTimer = setTimeout(() => this.loadProducts(false), 1200);
    }
  }

  renderProductList() {
    const container = document.getElementById("productList");
    container.innerHTML = "";
    this.products.forEach((prod) => {
      const card = document.createElement("div");
      card.className = `product-card ${
        this.activeProduct && this.activeProduct.id === prod.id ? "active" : ""
      }`;

      const thumbSrc = prod.thumbnail_url || "/assets/img-placeholder.svg";
      const isDone = prod.status === "completed";
      const badgeClass = isDone ? "badge-completed" : "badge-processing";
      const badgeLabel = isDone ? `${prod.frame_count} góc • ${prod.package_size_mb}MB` : `${prod.stage} (${prod.progress}%)`;

      card.innerHTML = `
        <img class="product-thumb" src="${thumbSrc}" alt="${prod.name}" onerror="this.style.opacity=0.2" />
        <div class="product-meta">
          <div class="product-name">${prod.name}</div>
          <div class="product-sub">
            <span class="badge ${badgeClass}">${badgeLabel}</span>
          </div>
        </div>
      `;
      card.addEventListener("click", () => this.selectProduct(prod.id));
      container.appendChild(card);
    });
  }

  async selectProduct(productId) {
    const res = await fetch(`/api/products/${productId}`);
    if (!res.ok) return;
    const prod = await res.json();
    this.activeProduct = prod;
    this.renderProductList();

    document.getElementById("activeProductTitle").textContent = prod.name;
    document.getElementById("activeProductDesc").textContent =
      prod.description || `${prod.category} • Mã rút gọn: ${prod.short_code}`;

    const scrubber = document.getElementById("frameScrubber");
    scrubber.max = String(Math.max(0, (prod.frame_count || 36) - 1));
    scrubber.value = "0";

    this.hideHotspotPopover();
    this.updateRightSidebar(prod);

    if (prod.status === "completed") {
      await this.viewer.loadProduct(prod);
    }
  }

  updateRightSidebar(prod) {
    const m = prod.metrics || {};
    const timeEl = document.getElementById("metricTime");
    const sizeEl = document.getElementById("metricSize");
    const jitterEl = document.getElementById("metricRawJitter");

    timeEl.textContent = prod.processing_time_sec ? `${prod.processing_time_sec}s` : "Đang xử lý...";
    sizeEl.textContent = prod.package_size_mb ? `${prod.package_size_mb} MB` : "-- MB";
    jitterEl.textContent =
      m.raw_centroid_jitter_px !== undefined ? `±${m.raw_centroid_jitter_px} px` : "-- px";

    const fullShareUrl = `${window.location.origin}${prod.share_url}`;
    document.getElementById("shortLinkText").textContent = fullShareUrl;
    document.getElementById("openPublicViewerLink").href = prod.share_url;
    document.getElementById("downloadIndexJsonBtn").href = prod.index_json_url || "#";

    // Render Hotspots list
    const hotspots = prod.hotspots || [];
    document.getElementById("hotspotCountBadge").textContent = `${hotspots.length} điểm`;
    const listEl = document.getElementById("hotspotList");
    listEl.innerHTML = "";

    hotspots.forEach((hs, idx) => {
      const item = document.createElement("div");
      item.className = "hotspot-item";
      const deg = Math.round((hs.frame_index / Math.max(1, prod.frame_count || 36)) * 360);
      item.innerHTML = `
        <div style="flex:1;">
          <div style="font-size:12.5px;font-weight:700;color:var(--accent-primary);">
            #${idx + 1} ${hs.title} <span style="color:var(--text-secondary);font-weight:500;">(${deg}°)</span>
          </div>
          <div style="font-size:11.5px;color:var(--text-secondary);margin-top:2px;">
            ${hs.description || ""}
          </div>
        </div>
        <button type="button" class="btn btn-sm btn-secondary" data-del-hs="${hs.id}" title="Xóa điểm nhấn">✕</button>
      `;

      item.addEventListener("click", (e) => {
        if (e.target.closest("[data-del-hs]")) return;
        this.viewer.rotateToFrame(hs.frame_index);
        this.showHotspotPopover(hs);
      });

      const delBtn = item.querySelector("[data-del-hs]");
      delBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        await this.deleteHotspot(hs.id);
      });

      listEl.appendChild(item);
    });
  }

  handleFrameChange(frameIdx, totalFrames) {
    const deg = Math.round((frameIdx / Math.max(1, totalFrames)) * 360);
    document.getElementById("angleValueText").textContent = `${deg}°`;
    document.getElementById("frameIndexText").textContent = `${frameIdx + 1}/${totalFrames}`;
    document.getElementById("frameScrubber").value = String(frameIdx);
  }

  handleLoadProgress(loaded, total, elapsedMs) {
    const label = document.getElementById("loadSpeedLabel");
    if (loaded === 1) {
      label.textContent = `Khởi tải: ${Math.round(elapsedMs)}ms (NFR-01 < 2000ms)`;
    } else if (loaded === total) {
      label.textContent = `360° Sẵn sàng (${Math.round(elapsedMs)}ms)`;
    } else {
      label.textContent = `Đang nạp ${loaded}/${total}...`;
    }
  }

  showHotspotPopover(hs) {
    const pop = document.getElementById("hotspotPopover");
    const typeLabels = {
      material: "Chất liệu",
      dimension: "Kích thước",
      detail: "Chi tiết",
      defect: "Tình trạng / Lỗi nhỏ",
    };
    document.getElementById("popoverTagBadge").textContent = typeLabels[hs.tag_type] || "Chi tiết";
    document.getElementById("popoverTitle").textContent = hs.title;
    document.getElementById("popoverDesc").textContent = hs.description || "";
    pop.classList.add("visible");
  }

  hideHotspotPopover() {
    document.getElementById("hotspotPopover").classList.remove("visible");
  }

  openCreateHotspotModal(coords) {
    if (!this.activeProduct) return;
    this.pendingPinCoord = coords;
    this.viewer.setPinPlacementMode(false);
    document.getElementById("togglePinModeBtn").textContent = "📍 Gắn Điểm Nhấn (Hotspot)";

    const deg = Math.round(
      (coords.frame_index / Math.max(1, this.activeProduct.frame_count || 36)) * 360
    );
    document.getElementById("hsFrameDisplay").value = `Frame #${coords.frame_index + 1} (${deg}°) — X:${Math.round(coords.x * 100)}%, Y:${Math.round(coords.y * 100)}%`;
    document.getElementById("hsTitleInput").value = "";
    document.getElementById("hsDescInput").value = "";

    const dlg = document.getElementById("hotspotDialog");
    dlg.showModal();
  }

  async deleteHotspot(hotspotId) {
    if (!this.activeProduct) return;
    const res = await fetch(
      `/api/products/${this.activeProduct.id}/hotspots/${hotspotId}`,
      { method: "DELETE" }
    );
    if (res.ok) {
      const updated = await res.json();
      this.activeProduct = updated;
      this.viewer.setHotspots(updated.hotspots);
      this.updateRightSidebar(updated);
      this.hideHotspotPopover();
    }
  }

  bindUI() {
    // 1. Preset 360 Demo Generators
    document.querySelectorAll(".preset-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const preset = btn.getAttribute("data-preset");
        btn.disabled = true;
        try {
          const res = await fetch("/api/products/demo", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ preset, frame_count: 36, ai_mode: "auto" }),
          });
          if (res.ok) {
            const created = await res.json();
            this.activeProduct = created;
            await this.loadProducts(false);
          }
        } finally {
          btn.disabled = false;
        }
      });
    });

    // 2. Refresh button
    document.getElementById("refreshListBtn").addEventListener("click", () => {
      this.loadProducts(false);
    });

    // 3. Scrubber
    document.getElementById("frameScrubber").addEventListener("input", (e) => {
      this.viewer.setAutoSpin(false);
      document.getElementById("autoSpinBtn").classList.remove("active");
      this.viewer.setFrame(Number(e.target.value));
    });

    // 4. Viewer HUD controls
    const autoSpinBtn = document.getElementById("autoSpinBtn");
    autoSpinBtn.addEventListener("click", () => {
      const next = !this.viewer.autoSpin;
      this.viewer.setAutoSpin(next);
      autoSpinBtn.classList.toggle("active", next);
      autoSpinBtn.textContent = next ? "⏸ Dừng xoay" : "▶ Tự xoay";
    });

    document.getElementById("zoomInBtn").addEventListener("click", () => {
      this.viewer.setZoom(this.viewer.zoom + 0.35);
      document.getElementById("zoomLevelText").textContent = `${this.viewer.zoom.toFixed(1)}x`;
    });

    document.getElementById("zoomOutBtn").addEventListener("click", () => {
      this.viewer.setZoom(this.viewer.zoom - 0.35);
      document.getElementById("zoomLevelText").textContent = `${this.viewer.zoom.toFixed(1)}x`;
    });

    // Theme switcher
    document.querySelectorAll("[data-theme]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const theme = btn.getAttribute("data-theme");
        const container = document.getElementById("viewerContainer");
        container.classList.remove("theme-dark", "theme-light", "theme-sand", "theme-checker");
        container.classList.add(theme);
      });
    });

    // Compare Before/After AI & Auto-Centering
    const compareBtn = document.getElementById("compareModeBtn");
    compareBtn.addEventListener("click", () => {
      const nextMode = this.viewer.viewMode === "processed" ? "raw" : "processed";
      this.viewer.setViewMode(nextMode);
      if (nextMode === "raw") {
        compareBtn.textContent = "⚠️ Đang xem: Ảnh Gốc (Chưa tách nền & Rung lắc)";
        compareBtn.style.borderColor = "#f59e0b";
      } else {
        compareBtn.textContent = "✨ Đang xem: Đã Tách Nền & Căn Tâm";
        compareBtn.style.borderColor = "rgba(56, 189, 248, 0.45)";
      }
    });

    // Pin placement mode
    const pinBtn = document.getElementById("togglePinModeBtn");
    pinBtn.addEventListener("click", () => {
      const next = !this.viewer.pinPlacementMode;
      this.viewer.setPinPlacementMode(next);
      pinBtn.textContent = next
        ? "🎯 Click lên sản phẩm để gắn điểm..."
        : "📍 Gắn Điểm Nhấn (Hotspot)";
    });

    document.getElementById("closePopoverBtn").addEventListener("click", () => {
      this.hideHotspotPopover();
    });

    // Hotspot Form Submit
    document.getElementById("hotspotForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!this.activeProduct || !this.pendingPinCoord) return;

      const payload = {
        frame_index: this.pendingPinCoord.frame_index,
        x: this.pendingPinCoord.x,
        y: this.pendingPinCoord.y,
        title: document.getElementById("hsTitleInput").value.trim(),
        description: document.getElementById("hsDescInput").value.trim(),
        tag_type: document.getElementById("hsTypeSelect").value,
        visible_range: 3,
      };

      const res = await fetch(`/api/products/${this.activeProduct.id}/hotspots`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        const updated = await res.json();
        this.activeProduct = updated;
        this.viewer.setHotspots(updated.hotspots);
        this.updateRightSidebar(updated);
        document.getElementById("hotspotDialog").close();
      }
    });

    // Upload Modal
    const uploadDlg = document.getElementById("uploadDialog");
    document.getElementById("openUploadModalBtn").addEventListener("click", () => {
      uploadDlg.showModal();
    });

    const tabVideoBtn = document.getElementById("tabTurntableBtn");
    const tabImagesBtn = document.getElementById("tabManualImagesBtn");
    tabVideoBtn.addEventListener("click", () => {
      document.getElementById("uploadModeInput").value = "video";
      document.getElementById("videoInputGroup").style.display = "block";
      document.getElementById("imagesInputGroup").style.display = "none";
      tabVideoBtn.className = "btn btn-primary";
      tabImagesBtn.className = "btn btn-secondary";
    });
    tabImagesBtn.addEventListener("click", () => {
      document.getElementById("uploadModeInput").value = "images";
      document.getElementById("videoInputGroup").style.display = "none";
      document.getElementById("imagesInputGroup").style.display = "block";
      tabImagesBtn.className = "btn btn-primary";
      tabVideoBtn.className = "btn btn-secondary";
    });

    document.getElementById("uploadForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const mode = document.getElementById("uploadModeInput").value;
      const fd = new FormData();
      fd.append("name", document.getElementById("prodNameInput").value.trim());
      fd.append("category", document.getElementById("prodCategoryInput").value.trim());
      fd.append("description", document.getElementById("prodDescInput").value.trim());
      fd.append("ai_mode", document.getElementById("aiModeSelect").value);

      let endpoint = "/api/products/capture-video";
      if (mode === "video") {
        const videoFile = document.getElementById("videoFileInput").files[0];
        if (!videoFile) {
          alert("Vui lòng chọn file video bàn xoay.");
          return;
        }
        fd.append("target_frames", document.getElementById("prodTargetFrames").value);
        fd.append("video", videoFile);
      } else {
        endpoint = "/api/products/capture-images";
        const imgFiles = document.getElementById("imageFilesInput").files;
        if (!imgFiles || imgFiles.length < 4) {
          alert("Vui lòng chọn tối thiểu 4 ảnh góc độ.");
          return;
        }
        for (let i = 0; i < imgFiles.length; i++) {
          fd.append("files", imgFiles[i]);
        }
      }

      const submitBtn = document.getElementById("submitUploadBtn");
      submitBtn.disabled = true;
      submitBtn.textContent = "Đang tải lên...";
      try {
        const res = await fetch(endpoint, { method: "POST", body: fd });
        if (!res.ok) {
          const err = await res.json();
          alert(err.detail || "Lỗi tải lên");
          return;
        }
        const created = await res.json();
        this.activeProduct = created;
        uploadDlg.close();
        await this.loadProducts(false);
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "🚀 Đẩy vào Hàng đợi AI";
      }
    });

    // Export MP4 Modal
    const exportDlg = document.getElementById("exportDialog");
    document.getElementById("openExportModalBtn").addEventListener("click", () => {
      document.getElementById("mp4ResultBox").style.display = "none";
      exportDlg.showModal();
    });

    document.getElementById("runMp4ExportBtn").addEventListener("click", async () => {
      if (!this.activeProduct) return;
      const btn = document.getElementById("runMp4ExportBtn");
      btn.disabled = true;
      btn.textContent = "⏳ Đang kết xuất Video MP4...";
      try {
        const res = await fetch(`/api/products/${this.activeProduct.id}/export-mp4`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            aspect_ratio: document.getElementById("exportAspectSelect").value,
            bg_theme: document.getElementById("exportThemeSelect").value,
            loops: Number(document.getElementById("exportLoopsSelect").value),
            fps: 24,
          }),
        });
        const data = await res.json();
        if (!res.ok) {
          alert(data.detail || "Không thể xuất MP4");
          return;
        }
        const videoEl = document.getElementById("mp4PreviewVideo");
        videoEl.src = data.video_url;
        videoEl.play().catch(() => {});
        const dl = document.getElementById("downloadMp4Link");
        dl.href = data.video_url;
        document.getElementById("mp4ResultBox").style.display = "block";
      } finally {
        btn.disabled = false;
        btn.textContent = "🎬 Kết xuất Video MP4 Ngay";
      }
    });

    // Copy Short Link
    document.getElementById("copyShortLinkBtn").addEventListener("click", () => {
      const txt = document.getElementById("shortLinkText").textContent;
      navigator.clipboard.writeText(txt);
      const btn = document.getElementById("copyShortLinkBtn");
      btn.textContent = "Đã Copy!";
      setTimeout(() => {
        btn.textContent = "Copy";
      }, 1500);
    });

    // Delete Product
    document.getElementById("deleteProductBtn").addEventListener("click", async () => {
      if (!this.activeProduct) return;
      if (!confirm(`Xóa sản phẩm "${this.activeProduct.name}"?`)) return;
      const res = await fetch(`/api/products/${this.activeProduct.id}`, {
        method: "DELETE",
      });
      if (res.ok) {
        this.activeProduct = null;
        await this.loadProducts(true);
      }
    });
  }
}

window.addEventListener("DOMContentLoaded", () => {
  new Pocket3DStudioApp();
});
