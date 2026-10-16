import 'dart:async';
import 'package:flutter/material.dart';
import '../models/product_model.dart';
import '../services/api_client.dart';
import 'guided_capture_screen.dart';
import 'preview_screen.dart';

class HomeScreen extends StatefulWidget {
  final Pocket3DApiClient apiClient;

  const HomeScreen({super.key, required this.apiClient});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final List<LocalCaptureDraft> _localDrafts = [];
  List<Product360> _cloudProducts = [];
  bool _loading = false;
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _refreshCloudProducts();
  }

  Future<void> _refreshCloudProducts() async {
    setState(() => _loading = true);
    try {
      final list = await widget.apiClient.listProducts();
      if (!mounted) return;
      setState(() => _cloudProducts = list);

      final anyProcessing = list.any(
        (p) => p.status == 'queued' || p.status == 'processing',
      );
      _pollTimer?.cancel();
      if (anyProcessing) {
        _pollTimer = Timer(
          const Duration(seconds: 2),
          _refreshCloudProducts,
        );
      }
    } catch (_) {
      // Backend might be offline or at a custom IP
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _startGuidedCapture() async {
    final draft = await Navigator.of(context).push<LocalCaptureDraft>(
      MaterialPageRoute(builder: (_) => const GuidedCaptureScreen()),
    );
    if (draft != null && mounted) {
      setState(() => _localDrafts.insert(0, draft));
      // Open immediate Local Preview (FR-02)
      final uploaded = await Navigator.of(context).push<Product360>(
        MaterialPageRoute(
          builder: (_) => Preview360Screen(
            apiClient: widget.apiClient,
            localDraft: draft,
          ),
        ),
      );
      if (uploaded != null) {
        _refreshCloudProducts();
      }
    }
  }

  Future<void> _triggerQuickDemo(String preset) async {
    try {
      await widget.apiClient.generateDemoProduct(preset: preset, frameCount: 36);
      await _refreshCloudProducts();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Không thể kết nối Backend: $e')),
        );
      }
    }
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0B0F19),
      appBar: AppBar(
        backgroundColor: const Color(0xFF111827),
        title: const Text('Pocket 3D Showcase'),
        actions: [
          IconButton(
            onPressed: _refreshCloudProducts,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        backgroundColor: const Color(0xFF0284C7),
        foregroundColor: Colors.white,
        onPressed: _startGuidedCapture,
        icon: const Icon(Icons.camera_enhance),
        label: const Text('Chụp 360° Mới (FR-01)'),
      ),
      body: RefreshIndicator(
        onRefresh: _refreshCloudProducts,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // Quick Demo Generator Card
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: const Color(0xFF161F33),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.white12),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Tạo Nhanh Sản Phẩm Mẫu 360° (Test AI Worker)',
                    style: TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.bold,
                        fontSize: 14),
                  ),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    children: [
                      ActionChip(
                        avatar: const Text('👟'),
                        label: const Text('Sneaker 360°'),
                        onPressed: () => _triggerQuickDemo('sneaker'),
                      ),
                      ActionChip(
                        avatar: const Text('⌚'),
                        label: const Text('Đồng Hồ Cơ'),
                        onPressed: () => _triggerQuickDemo('watch'),
                      ),
                      ActionChip(
                        avatar: const Text('🤖'),
                        label: const Text('Figure Mecha'),
                        onPressed: () => _triggerQuickDemo('figure'),
                      ),
                    ],
                  ),
                ],
              ),
            ),

            const SizedBox(height: 18),

            // FR-02: Local Preview Drafts
            if (_localDrafts.isNotEmpty) ...[
              const Text(
                'BẢN NHÁP CỤC BỘ TRÊN THIẾT BỊ (FR-02)',
                style: TextStyle(
                    color: Color(0xFF38BDF8),
                    fontSize: 12,
                    fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              ..._localDrafts.map(
                (d) => Card(
                  color: const Color(0xFF1E293B),
                  child: ListTile(
                    leading: const Icon(Icons.stay_current_portrait,
                        color: Color(0xFF38BDF8)),
                    title: Text(d.name,
                        style: const TextStyle(color: Colors.white)),
                    subtitle: Text(
                      '${d.captureMode} • ${d.targetFrames} góc (Chưa đẩy lên Cloud)',
                      style:
                          const TextStyle(color: Colors.white60, fontSize: 12),
                    ),
                    trailing: const Icon(Icons.chevron_right,
                        color: Colors.white54),
                    onTap: () {
                      Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => Preview360Screen(
                            apiClient: widget.apiClient,
                            localDraft: d,
                          ),
                        ),
                      );
                    },
                  ),
                ),
              ),
              const SizedBox(height: 18),
            ],

            // Cloud Processed 360 Products
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'KHO SẢN PHẨM 360° ĐÃ XỬ LÝ AI (${_cloudProducts.length})',
                  style: const TextStyle(
                      color: Colors.white70,
                      fontSize: 12,
                      fontWeight: FontWeight.bold),
                ),
                if (_loading)
                  const SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
              ],
            ),
            const SizedBox(height: 8),
            ..._cloudProducts.map(
              (prod) => Card(
                color: const Color(0xFF161F33),
                margin: const EdgeInsets.only(bottom: 10),
                child: ListTile(
                  leading: CircleAvatar(
                    backgroundColor: const Color(0xFF0F172A),
                    backgroundImage: prod.thumbnailUrl != null
                        ? NetworkImage(
                            widget.apiClient.resolveUrl(prod.thumbnailUrl!))
                        : null,
                    child: prod.thumbnailUrl == null
                        ? const Icon(Icons.threed_rotation)
                        : null,
                  ),
                  title: Text(
                    prod.name,
                    style: const TextStyle(
                        color: Colors.white, fontWeight: FontWeight.w600),
                  ),
                  subtitle: Text(
                    prod.status == 'completed'
                        ? '${prod.frameCount} góc WebP (${prod.packageSizeMb} MB) • AI: ${prod.processingTimeSec}s'
                        : 'Đang xử lý: ${prod.stage} (${prod.progress}%)',
                    style: TextStyle(
                      color: prod.status == 'completed'
                          ? const Color(0xFF34D399)
                          : const Color(0xFFFBBF24),
                      fontSize: 12,
                    ),
                  ),
                  trailing:
                      const Icon(Icons.open_in_new, color: Colors.white54),
                  onTap: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => Preview360Screen(
                          apiClient: widget.apiClient,
                          cloudProduct: prod,
                        ),
                      ),
                    );
                  },
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
