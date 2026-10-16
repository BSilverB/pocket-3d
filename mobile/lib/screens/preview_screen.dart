import 'dart:io';
import 'package:flutter/material.dart';
import 'package:share_plus/share_plus.dart';
import '../models/product_model.dart';
import '../services/api_client.dart';

class Preview360Screen extends StatefulWidget {
  final Pocket3DApiClient apiClient;
  final LocalCaptureDraft? localDraft;
  final Product360? cloudProduct;

  const Preview360Screen({
    super.key,
    required this.apiClient,
    this.localDraft,
    this.cloudProduct,
  });

  @override
  State<Preview360Screen> createState() => _Preview360ScreenState();
}

class _Preview360ScreenState extends State<Preview360Screen> {
  int _currentIndex = 0;
  double _zoom = 1.0;
  bool _isUploading = false;
  bool _isExportingMp4 = false;
  Product360? _product;

  @override
  void initState() {
    super.initState();
    _product = widget.cloudProduct;
  }

  int get _frameCount {
    if (_product != null && _product!.frames.isNotEmpty) {
      return _product!.frames.length;
    }
    if (widget.localDraft != null) {
      return widget.localDraft!.localImagePaths.length;
    }
    return 0;
  }

  Future<void> _uploadDraftToCloud() async {
    final draft = widget.localDraft;
    if (draft == null || _isUploading) return;

    setState(() => _isUploading = true);
    try {
      Product360 uploaded;
      if (draft.captureMode == 'turntable_video' &&
          draft.localVideoPath != null) {
        uploaded = await widget.apiClient.uploadTurntableVideo(
          name: draft.name,
          category: draft.category,
          targetFrames: draft.targetFrames,
          videoFile: File(draft.localVideoPath!),
        );
      } else {
        final files = draft.localImagePaths
            .where((p) => File(p).existsSync())
            .map((p) => File(p))
            .toList();
        if (files.length >= 4) {
          uploaded = await widget.apiClient.uploadMultiAngleImages(
            name: draft.name,
            category: draft.category,
            imageFiles: files,
          );
        } else {
          // If captured on simulator without real files, run synthetic AI pipeline
          uploaded = await widget.apiClient.generateDemoProduct(
            preset: 'sneaker',
            frameCount: draft.targetFrames,
          );
        }
      }
      if (!mounted) return;
      setState(() => _product = uploaded);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Đã đẩy lên AI Worker (Tách nền & Căn tâm tự động)!'),
        ),
      );
      Navigator.of(context).pop(uploaded);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Lỗi tải lên: $e')),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isUploading = false);
      }
    }
  }

  Future<void> _exportVideo(String ratio) async {
    if (_product == null || _isExportingMp4) return;
    setState(() => _isExportingMp4 = true);
    try {
      final url = await widget.apiClient.exportMp4(
        productId: _product!.id,
        aspectRatio: ratio,
      );
      if (!mounted) return;
      await Share.share('Video 360° (${_product!.name} - $ratio): $url');
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Lỗi xuất MP4: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _isExportingMp4 = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isLocalOnly = _product == null && widget.localDraft != null;
    final title = _product?.name ?? widget.localDraft?.name ?? 'Xem trước 360°';
    final total = _frameCount;
    final deg = total > 0 ? ((_currentIndex / total) * 360).round() : 0;

    return Scaffold(
      backgroundColor: const Color(0xFF0B0F19),
      appBar: AppBar(
        backgroundColor: const Color(0xFF111827),
        title: Text(title),
        actions: [
          if (_product != null)
            IconButton(
              tooltip: 'Chia sẻ Link 360° (Zalo / Facebook)',
              icon: const Icon(Icons.share, color: Color(0xFF38BDF8)),
              onPressed: () {
                final publicLink =
                    widget.apiClient.resolveUrl(_product!.shareUrl);
                Share.share(
                    'Xem chi tiết 360° sản phẩm ${_product!.name}: $publicLink');
              },
            ),
        ],
      ),
      body: Column(
        children: [
          // Top Telemetry Banner
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            color: const Color(0xFF161F33),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  isLocalOnly
                      ? 'FR-02: Xem trước cục bộ (Chưa tách nền)'
                      : 'Gói WebP: ${_product!.packageSizeMb} MB • Xử lý AI: ${_product!.processingTimeSec}s',
                  style: const TextStyle(color: Colors.white70, fontSize: 12.5),
                ),
                Text(
                  'Góc $deg° (${_currentIndex + 1}/${total > 0 ? total : 1})',
                  style: const TextStyle(
                      color: Color(0xFF38BDF8),
                      fontWeight: FontWeight.bold,
                      fontSize: 12.5),
                ),
              ],
            ),
          ),

          // Interactive 360° Swipe & Zoom Viewport
          Expanded(
            child: GestureDetector(
              onHorizontalDragUpdate: (details) {
                if (total <= 0) return;
                if (details.primaryDelta != null &&
                    details.primaryDelta!.abs() > 2.5) {
                  final delta = details.primaryDelta! < 0 ? 1 : -1;
                  setState(() {
                    _currentIndex = (_currentIndex + delta + total) % total;
                  });
                }
              },
              child: Center(
                child: Transform.scale(
                  scale: _zoom,
                  child: _buildActiveFrameWidget(),
                ),
              ),
            ),
          ),

          // Scrubber + Zoom Controls
          Container(
            padding: const EdgeInsets.all(16),
            color: const Color(0xFF111827),
            child: Column(
              children: [
                if (total > 1)
                  Slider(
                    value: _currentIndex.toDouble().clamp(0, (total - 1).toDouble()),
                    min: 0,
                    max: (total - 1).toDouble(),
                    activeColor: const Color(0xFF38BDF8),
                    onChanged: (v) => setState(() => _currentIndex = v.round()),
                  ),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Row(
                      children: [
                        IconButton(
                          onPressed: () => setState(
                              () => _zoom = (_zoom - 0.25).clamp(1.0, 3.0)),
                          icon: const Icon(Icons.remove_circle_outline,
                              color: Colors.white70),
                        ),
                        Text('${_zoom.toStringAsFixed(1)}x',
                            style: const TextStyle(color: Colors.white)),
                        IconButton(
                          onPressed: () => setState(
                              () => _zoom = (_zoom + 0.25).clamp(1.0, 3.0)),
                          icon: const Icon(Icons.add_circle_outline,
                              color: Colors.white70),
                        ),
                      ],
                    ),
                    if (isLocalOnly)
                      ElevatedButton.icon(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF10B981),
                          foregroundColor: Colors.white,
                        ),
                        onPressed: _isUploading ? null : _uploadDraftToCloud,
                        icon: const Icon(Icons.cloud_upload),
                        label: Text(_isUploading
                            ? 'Đang đẩy lên AI...'
                            : 'Đẩy lên Cloud AI (FR-03)'),
                      )
                    else
                      Row(
                        children: [
                          OutlinedButton.icon(
                            onPressed: _isExportingMp4
                                ? null
                                : () => _exportVideo('9:16'),
                            icon: const Icon(Icons.movie_creation_outlined,
                                size: 16),
                            label: const Text('MP4 9:16'),
                          ),
                          const SizedBox(width: 8),
                          OutlinedButton.icon(
                            onPressed: _isExportingMp4
                                ? null
                                : () => _exportVideo('1:1'),
                            icon: const Icon(Icons.crop_square, size: 16),
                            label: const Text('MP4 1:1'),
                          ),
                        ],
                      ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActiveFrameWidget() {
    if (_product != null && _product!.frames.isNotEmpty) {
      final url = widget.apiClient.resolveUrl(_product!.frames[_currentIndex]);
      return Image.network(
        url,
        fit: BoxFit.contain,
        gaplessPlayback: true,
      );
    }
    if (widget.localDraft != null &&
        widget.localDraft!.localImagePaths.isNotEmpty) {
      final path = widget.localDraft!.localImagePaths[_currentIndex];
      final file = File(path);
      if (file.existsSync()) {
        return Image.file(file, fit: BoxFit.contain, gaplessPlayback: true);
      }
    }
    return const Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(Icons.threed_rotation, size: 72, color: Color(0xFF38BDF8)),
        SizedBox(height: 12),
        Text(
          'Vuốt ngang để kiểm tra góc xoay 360°\nBấm "Đẩy lên Cloud AI" để tách nền & căn tâm tự động',
          textAlign: TextAlign.center,
          style: TextStyle(color: Colors.white70),
        ),
      ],
    );
  }
}
