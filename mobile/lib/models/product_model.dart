class HotspotPin {
  final String id;
  final int frameIndex;
  final double x;
  final double y;
  final String title;
  final String description;
  final String tagType;
  final int visibleRange;

  const HotspotPin({
    required this.id,
    required this.frameIndex,
    required this.x,
    required this.y,
    required this.title,
    this.description = '',
    this.tagType = 'detail',
    this.visibleRange = 3,
  });

  factory HotspotPin.fromJson(Map<String, dynamic> json) {
    return HotspotPin(
      id: json['id']?.toString() ?? '',
      frameIndex: (json['frame_index'] as num?)?.toInt() ?? 0,
      x: (json['x'] as num?)?.toDouble() ?? 0.5,
      y: (json['y'] as num?)?.toDouble() ?? 0.5,
      title: json['title']?.toString() ?? '',
      description: json['description']?.toString() ?? '',
      tagType: json['tag_type']?.toString() ?? 'detail',
      visibleRange: (json['visible_range'] as num?)?.toInt() ?? 3,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'frame_index': frameIndex,
        'x': x,
        'y': y,
        'title': title,
        'description': description,
        'tag_type': tagType,
        'visible_range': visibleRange,
      };
}

class LocalCaptureDraft {
  final String id;
  final String name;
  final String category;
  final String captureMode; // 'manual_gyro' | 'turntable_video'
  final int targetFrames;
  final List<String> localImagePaths;
  final String? localVideoPath;
  final DateTime createdAt;

  const LocalCaptureDraft({
    required this.id,
    required this.name,
    required this.category,
    required this.captureMode,
    required this.targetFrames,
    this.localImagePaths = const [],
    this.localVideoPath,
    required this.createdAt,
  });
}

class Product360 {
  final String id;
  final String shortCode;
  final String name;
  final String category;
  final String description;
  final String captureMode;
  final int targetFrames;
  final int frameCount;
  final int canvasSize;
  final String status;
  final int progress;
  final String stage;
  final double processingTimeSec;
  final double packageSizeMb;
  final String? thumbnailUrl;
  final String shareUrl;
  final String viewerUrl;
  final List<String> frames;
  final List<String> rawFrames;
  final List<HotspotPin> hotspots;
  final Map<String, dynamic> exports;
  final Map<String, dynamic> metrics;

  const Product360({
    required this.id,
    required this.shortCode,
    required this.name,
    required this.category,
    required this.description,
    required this.captureMode,
    required this.targetFrames,
    required this.frameCount,
    required this.canvasSize,
    required this.status,
    required this.progress,
    required this.stage,
    required this.processingTimeSec,
    required this.packageSizeMb,
    this.thumbnailUrl,
    required this.shareUrl,
    required this.viewerUrl,
    required this.frames,
    required this.rawFrames,
    required this.hotspots,
    required this.exports,
    required this.metrics,
  });

  factory Product360.fromJson(Map<String, dynamic> json) {
    final framesList = (json['frames'] as List<dynamic>? ?? [])
        .map((e) => e.toString())
        .toList();
    final rawList = (json['raw_frames'] as List<dynamic>? ?? [])
        .map((e) => e.toString())
        .toList();
    final hsList = (json['hotspots'] as List<dynamic>? ?? [])
        .map((e) => HotspotPin.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();

    return Product360(
      id: json['id']?.toString() ?? '',
      shortCode: json['short_code']?.toString() ?? '',
      name: json['name']?.toString() ?? 'Untitled',
      category: json['category']?.toString() ?? 'General',
      description: json['description']?.toString() ?? '',
      captureMode: json['capture_mode']?.toString() ?? 'manual_gyro',
      targetFrames: (json['target_frames'] as num?)?.toInt() ?? 36,
      frameCount: (json['frame_count'] as num?)?.toInt() ?? 0,
      canvasSize: (json['canvas_size'] as num?)?.toInt() ?? 800,
      status: json['status']?.toString() ?? 'queued',
      progress: (json['progress'] as num?)?.toInt() ?? 0,
      stage: json['stage']?.toString() ?? 'queued',
      processingTimeSec: (json['processing_time_sec'] as num?)?.toDouble() ?? 0.0,
      packageSizeMb: (json['package_size_mb'] as num?)?.toDouble() ?? 0.0,
      thumbnailUrl: json['thumbnail_url']?.toString(),
      shareUrl: json['share_url']?.toString() ?? '',
      viewerUrl: json['viewer_url']?.toString() ?? '',
      frames: framesList,
      rawFrames: rawList,
      hotspots: hsList,
      exports: Map<String, dynamic>.from(json['exports'] as Map? ?? {}),
      metrics: Map<String, dynamic>.from(json['metrics'] as Map? ?? {}),
    );
  }
}
