import 'dart:async';
import 'dart:math' as math;
import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:sensors_plus/sensors_plus.dart';
import '../models/product_model.dart';

enum CaptureModeType { manualGyro, turntableVideo }

class GuidedCaptureScreen extends StatefulWidget {
  const GuidedCaptureScreen({super.key});

  @override
  State<GuidedCaptureScreen> createState() => _GuidedCaptureScreenState();
}

class _GuidedCaptureScreenState extends State<GuidedCaptureScreen> {
  CameraController? _cameraController;
  bool _cameraReady = false;

  CaptureModeType _mode = CaptureModeType.manualGyro;
  int _targetSlots = 36; // 24 or 36 angles (FR-01)
  bool _autoShutterEnabled = true;

  // Gyroscope integration state (Manual Gyro Mode)
  StreamSubscription<GyroscopeEvent>? _gyroSub;
  double _currentYawDeg = 0.0;
  DateTime? _lastGyroTime;
  final Map<int, String> _capturedSlotPaths = {};
  bool _isTakingPicture = false;

  // Turntable Video Mode state (10-12s)
  bool _isRecordingVideo = false;
  int _turntableDurationSec = 11;
  double _recordingProgress = 0.0;
  Timer? _recordingTimer;

  final TextEditingController _nameCtrl =
      TextEditingController(text: 'Sản phẩm 360° Mới');
  final TextEditingController _categoryCtrl =
      TextEditingController(text: 'Sneakers / Đồng hồ / Figure');

  @override
  void initState() {
    super.initState();
    _initCamera();
    _initGyroscope();
  }

  Future<void> _initCamera() async {
    try {
      final cameras = await availableCameras();
      if (cameras.isNotEmpty) {
        final ctrl = CameraController(
          cameras.first,
          ResolutionPreset.high,
          enableAudio: false,
        );
        await ctrl.initialize();
        if (mounted) {
          setState(() {
            _cameraController = ctrl;
            _cameraReady = true;
          });
        }
      }
    } catch (_) {
      // Camera may be unavailable on desktop/emulator; Simulator slider remains usable
    }
  }

  void _initGyroscope() {
    _gyroSub = gyroscopeEventStream().listen((GyroscopeEvent event) {
      final now = DateTime.now();
      if (_lastGyroTime != null && _mode == CaptureModeType.manualGyro) {
        final dt = now.difference(_lastGyroTime!).inMicroseconds / 1e6;
        // Integrate Y-axis angular velocity (rad/s -> degrees)
        final deltaDeg = event.y * (180.0 / math.pi) * dt;
        if (deltaDeg.abs() > 0.08) {
          setState(() {
            _currentYawDeg = (_currentYawDeg + deltaDeg) % 360.0;
            if (_currentYawDeg < 0) _currentYawDeg += 360.0;
          });
          _checkAutoTrigger();
        }
      }
      _lastGyroTime = now;
    });
  }

  int get _currentSlotIndex {
    final stepDeg = 360.0 / _targetSlots;
    return ((_currentYawDeg / stepDeg).round()) % _targetSlots;
  }

  Future<void> _checkAutoTrigger() async {
    if (!_autoShutterEnabled || _isTakingPicture) return;
    final slot = _currentSlotIndex;
    if (_capturedSlotPaths.containsKey(slot)) return;

    final stepDeg = 360.0 / _targetSlots;
    final slotCenterDeg = slot * stepDeg;
    double diff = (_currentYawDeg - slotCenterDeg).abs();
    if (diff > 180) diff = 360 - diff;

    // Trigger when aligned within +/- 2.2 degrees of the target slot
    if (diff <= 2.2) {
      await _captureCurrentSlot(slot);
    }
  }

  Future<void> _captureCurrentSlot(int slot) async {
    if (_isTakingPicture) return;
    setState(() => _isTakingPicture = true);
    try {
      String filePath = 'simulated_frame_$slot.jpg';
      if (_cameraReady && _cameraController != null) {
        final xfile = await _cameraController!.takePicture();
        filePath = xfile.path;
      }
      if (!mounted) return;
      setState(() {
        _capturedSlotPaths[slot] = filePath;
      });

      if (_capturedSlotPaths.length >= _targetSlots) {
        _finishManualGyroCapture();
      }
    } finally {
      if (mounted) {
        setState(() => _isTakingPicture = false);
      }
    }
  }

  void _finishManualGyroCapture() {
    final sortedSlots = _capturedSlotPaths.keys.toList()..sort();
    final orderedPaths = sortedSlots.map((k) => _capturedSlotPaths[k]!).toList();
    final draft = LocalCaptureDraft(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      name: _nameCtrl.text.trim(),
      category: _categoryCtrl.text.trim(),
      captureMode: 'manual_gyro',
      targetFrames: _targetSlots,
      localImagePaths: orderedPaths,
      createdAt: DateTime.now(),
    );
    Navigator.of(context).pop(draft);
  }

  Future<void> _toggleTurntableRecording() async {
    if (_isRecordingVideo) return;
    setState(() {
      _isRecordingVideo = true;
      _recordingProgress = 0.0;
    });

    if (_cameraReady && _cameraController != null) {
      try {
        await _cameraController!.startVideoRecording();
      } catch (_) {}
    }

    const tickMs = 100;
    final totalTicks = (_turntableDurationSec * 1000) ~/ tickMs;
    int currentTick = 0;

    _recordingTimer =
        Timer.periodic(const Duration(milliseconds: tickMs), (timer) async {
      currentTick++;
      if (!mounted) {
        timer.cancel();
        return;
      }
      setState(() {
        _recordingProgress = (currentTick / totalTicks).clamp(0.0, 1.0);
      });

      if (currentTick >= totalTicks) {
        timer.cancel();
        String? videoPath;
        if (_cameraReady && _cameraController != null) {
          try {
            final xfile = await _cameraController!.stopVideoRecording();
            videoPath = xfile.path;
          } catch (_) {}
        }
        if (!mounted) return;
        setState(() => _isRecordingVideo = false);
        final draft = LocalCaptureDraft(
          id: DateTime.now().millisecondsSinceEpoch.toString(),
          name: _nameCtrl.text.trim(),
          category: _categoryCtrl.text.trim(),
          captureMode: 'turntable_video',
          targetFrames: _targetSlots,
          localVideoPath: videoPath,
          createdAt: DateTime.now(),
        );
        Navigator.of(context).pop(draft);
      }
    });
  }

  Future<void> _pickFromGallery() async {
    final picker = ImagePicker();
    if (_mode == CaptureModeType.turntableVideo) {
      final video = await picker.pickVideo(source: ImageSource.gallery);
      if (video != null && mounted) {
        Navigator.of(context).pop(
          LocalCaptureDraft(
            id: DateTime.now().millisecondsSinceEpoch.toString(),
            name: _nameCtrl.text.trim(),
            category: _categoryCtrl.text.trim(),
            captureMode: 'turntable_video',
            targetFrames: _targetSlots,
            localVideoPath: video.path,
            createdAt: DateTime.now(),
          ),
        );
      }
    } else {
      final images = await picker.pickMultiImage();
      if (images.length >= 4 && mounted) {
        Navigator.of(context).pop(
          LocalCaptureDraft(
            id: DateTime.now().millisecondsSinceEpoch.toString(),
            name: _nameCtrl.text.trim(),
            category: _categoryCtrl.text.trim(),
            captureMode: 'manual_gyro',
            targetFrames: images.length,
            localImagePaths: images.map((e) => e.path).toList(),
            createdAt: DateTime.now(),
          ),
        );
      }
    }
  }

  @override
  void dispose() {
    _gyroSub?.cancel();
    _recordingTimer?.cancel();
    _cameraController?.dispose();
    _nameCtrl.dispose();
    _categoryCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0B0F19),
      appBar: AppBar(
        backgroundColor: const Color(0xFF111827),
        title: const Text('FR-01: Chụp Hướng Dẫn Thông Minh'),
        actions: [
          TextButton.icon(
            onPressed: _pickFromGallery,
            icon: const Icon(Icons.photo_library_outlined,
                color: Color(0xFF38BDF8)),
            label: const Text('Thư viện',
                style: TextStyle(color: Color(0xFF38BDF8))),
          ),
        ],
      ),
      body: Column(
        children: [
          // Mode Selector Bar (Manual Gyro vs Turntable Video)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            color: const Color(0xFF111827),
            child: Row(
              children: [
                Expanded(
                  child: SegmentedButton<CaptureModeType>(
                    segments: const [
                      ButtonSegment(
                        value: CaptureModeType.manualGyro,
                        icon: Icon(Icons.explore_outlined),
                        label: Text('Thủ công (Gyro)'),
                      ),
                      ButtonSegment(
                        value: CaptureModeType.turntableVideo,
                        icon: Icon(Icons.album_outlined),
                        label: Text('Bàn xoay (Video)'),
                      ),
                    ],
                    selected: {_mode},
                    onSelectionChanged: (s) {
                      setState(() => _mode = s.first);
                    },
                  ),
                ),
                const SizedBox(width: 10),
                DropdownButton<int>(
                  value: _targetSlots,
                  dropdownColor: const Color(0xFF1E293B),
                  style: const TextStyle(color: Colors.white, fontSize: 13),
                  items: const [
                    DropdownMenuItem(value: 24, child: Text('24 Góc')),
                    DropdownMenuItem(value: 36, child: Text('36 Góc')),
                  ],
                  onChanged: (v) {
                    if (v != null) {
                      setState(() {
                        _targetSlots = v;
                        _capturedSlotPaths.clear();
                      });
                    }
                  },
                ),
              ],
            ),
          ),

          // Camera Viewport + Bounding Box + 360° Guided Angle Ring Overlay
          Expanded(
            child: Stack(
              fit: StackFit.expand,
              children: [
                if (_cameraReady && _cameraController != null)
                  CameraPreview(_cameraController!)
                else
                  Container(
                    decoration: const BoxDecoration(
                      gradient: RadialGradient(
                        colors: [Color(0xFF1E293B), Color(0xFF090D16)],
                        radius: 0.9,
                      ),
                    ),
                    child: const Center(
                      child: Text(
                        'Chế độ Mô Phỏng Cảm Biến Camera & Gyroscope\n(Dùng thanh trượt góc bên dưới để test trên máy ảo)',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: Colors.white54, fontSize: 13),
                      ),
                    ),
                  ),

                // Custom Painter: Bounding Box + 360° Compass Angle Ring
                CustomPaint(
                  painter: _GuidedOverlayPainter(
                    mode: _mode,
                    targetSlots: _targetSlots,
                    currentYawDeg: _currentYawDeg,
                    capturedSlots: _capturedSlotPaths.keys.toSet(),
                    recordingProgress: _recordingProgress,
                  ),
                ),

                // Top Status HUD
                Positioned(
                  top: 16,
                  left: 16,
                  right: 16,
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 12, vertical: 6),
                        decoration: BoxDecoration(
                          color: Colors.black87,
                          borderRadius: BorderRadius.circular(99),
                          border: Border.all(color: Colors.white24),
                        ),
                        child: Text(
                          _mode == CaptureModeType.manualGyro
                              ? 'Đã chụp: ${_capturedSlotPaths.length}/$_targetSlots góc • Góc: ${_currentYawDeg.toStringAsFixed(0)}°'
                              : 'Bàn xoay $_turntableDurationSec giây • Trích xuất $_targetSlots frame',
                          style: const TextStyle(
                              color: Colors.white,
                              fontSize: 12,
                              fontWeight: FontWeight.w600),
                        ),
                      ),
                      if (_mode == CaptureModeType.manualGyro)
                        FilterChip(
                          label: const Text('Auto-Chụp'),
                          selected: _autoShutterEnabled,
                          onSelected: (v) =>
                              setState(() => _autoShutterEnabled = v),
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),

          // Bottom Control Bar
          Container(
            padding: const EdgeInsets.all(16),
            color: const Color(0xFF111827),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (_mode == CaptureModeType.manualGyro) ...[
                  // Emulator / Simulator Gyro Angle Scrubber
                  Row(
                    children: [
                      const Text('Giả lập góc Gyro:',
                          style:
                              TextStyle(color: Colors.white70, fontSize: 12)),
                      Expanded(
                        child: Slider(
                          value: _currentYawDeg,
                          min: 0,
                          max: 359,
                          activeColor: const Color(0xFF38BDF8),
                          onChanged: (val) {
                            setState(() => _currentYawDeg = val);
                            _checkAutoTrigger();
                          },
                        ),
                      ),
                    ],
                  ),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                    children: [
                      OutlinedButton.icon(
                        onPressed: () {
                          setState(() => _capturedSlotPaths.clear());
                        },
                        icon: const Icon(Icons.refresh),
                        label: const Text('Chụp lại'),
                      ),
                      ElevatedButton.icon(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF0284C7),
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(
                              horizontal: 24, vertical: 12),
                        ),
                        onPressed: () =>
                            _captureCurrentSlot(_currentSlotIndex),
                        icon: const Icon(Icons.camera_alt),
                        label: Text('Chụp Góc #${_currentSlotIndex + 1}'),
                      ),
                      if (_capturedSlotPaths.length >= 4)
                        FilledButton.tonalIcon(
                          onPressed: _finishManualGyroCapture,
                          icon: const Icon(Icons.check_circle),
                          label: const Text('Hoàn tất'),
                        ),
                    ],
                  ),
                ] else ...[
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      ElevatedButton.icon(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: _isRecordingVideo
                              ? Colors.redAccent
                              : const Color(0xFF10B981),
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(
                              horizontal: 28, vertical: 14),
                        ),
                        onPressed: _isRecordingVideo
                            ? null
                            : _toggleTurntableRecording,
                        icon: Icon(_isRecordingVideo
                            ? Icons.fiber_manual_record
                            : Icons.videocam),
                        label: Text(
                          _isRecordingVideo
                              ? 'Đang quay bàn xoay... ${(100 * _recordingProgress).toInt()}%'
                              : 'Bắt đầu quay Bàn xoay ($_turntableDurationSec giây)',
                        ),
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _GuidedOverlayPainter extends CustomPainter {
  final CaptureModeType mode;
  final int targetSlots;
  final double currentYawDeg;
  final Set<int> capturedSlots;
  final double recordingProgress;

  _GuidedOverlayPainter({
    required this.mode,
    required this.targetSlots,
    required this.currentYawDeg,
    required this.capturedSlots,
    required this.recordingProgress,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final boxSize = math.min(size.width, size.height) * 0.64;
    final boxRect =
        Rect.fromCenter(center: center, width: boxSize, height: boxSize);

    // 1. Draw Product Bounding Box (FR-01)
    final boxPaint = Paint()
      ..color = const Color(0xFF38BDF8).withOpacity(0.55)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.0;
    canvas.drawRRect(
      RRect.fromRectAndRadius(boxRect, const Radius.circular(16)),
      boxPaint,
    );

    // Center crosshair inside bounding box so user keeps object centered
    final crossPaint = Paint()
      ..color = Colors.white38
      ..strokeWidth = 1.5;
    canvas.drawLine(
        Offset(center.dx - 14, center.dy), Offset(center.dx + 14, center.dy), crossPaint);
    canvas.drawLine(
        Offset(center.dx, center.dy - 14), Offset(center.dx, center.dy + 14), crossPaint);

    // 2. Draw 360° Guided Angle Ring around the Bounding Box
    final ringRadius = boxSize * 0.62;
    if (mode == CaptureModeType.manualGyro) {
      for (int i = 0; i < targetSlots; i++) {
        final angleRad = (i * 2 * math.pi / targetSlots) - math.pi / 2;
        final isCaptured = capturedSlots.contains(i);
        final p1 = Offset(
          center.dx + (ringRadius - 8) * math.cos(angleRad),
          center.dy + (ringRadius - 8) * math.sin(angleRad),
        );
        final p2 = Offset(
          center.dx + (ringRadius + 8) * math.cos(angleRad),
          center.dy + (ringRadius + 8) * math.sin(angleRad),
        );

        final tickPaint = Paint()
          ..color =
              isCaptured ? const Color(0xFF10B981) : Colors.white.withOpacity(0.32)
          ..strokeWidth = isCaptured ? 4.0 : 2.2
          ..strokeCap = StrokeCap.round;
        canvas.drawLine(p1, p2, tickPaint);
      }

      // Draw active Gyro cursor orb on the ring
      final cursorRad = (currentYawDeg * math.pi / 180.0) - math.pi / 2;
      final cursorPos = Offset(
        center.dx + ringRadius * math.cos(cursorRad),
        center.dy + ringRadius * math.sin(cursorRad),
      );
      canvas.drawCircle(
        cursorPos,
        9,
        Paint()..color = const Color(0xFF38BDF8),
      );
    } else {
      // Turntable Circular Progress Ring
      final bgRing = Paint()
        ..color = Colors.white24
        ..style = PaintingStyle.stroke
        ..strokeWidth = 6.0;
      canvas.drawCircle(center, ringRadius, bgRing);

      final fgRing = Paint()
        ..color = const Color(0xFF10B981)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 6.0
        ..strokeCap = StrokeCap.round;
      canvas.drawArc(
        Rect.fromCircle(center: center, radius: ringRadius),
        -math.pi / 2,
        2 * math.pi * recordingProgress,
        false,
        fgRing,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _GuidedOverlayPainter oldDelegate) => true;
}
