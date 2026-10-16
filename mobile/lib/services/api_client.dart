import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../models/product_model.dart';

class Pocket3DApiClient {
  String baseUrl;

  Pocket3DApiClient({this.baseUrl = 'http://10.0.2.2:8000'});

  String resolveUrl(String relativeOrFull) {
    if (relativeOrFull.startsWith('http://') ||
        relativeOrFull.startsWith('https://')) {
      return relativeOrFull;
    }
    return '$baseUrl${relativeOrFull.startsWith('/') ? '' : '/'}$relativeOrFull';
  }

  Future<List<Product360>> listProducts() async {
    final res = await http.get(Uri.parse('$baseUrl/api/products'));
    if (res.statusCode != 200) {
      throw Exception('Failed to load products: ${res.statusCode}');
    }
    final List<dynamic> list = jsonDecode(utf8.decode(res.bodyBytes));
    return list
        .map((e) => Product360.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
  }

  Future<Product360> getProduct(String productId) async {
    final res = await http.get(Uri.parse('$baseUrl/api/products/$productId'));
    if (res.statusCode != 200) {
      throw Exception('Product not found: ${res.statusCode}');
    }
    return Product360.fromJson(
        Map<String, dynamic>.from(jsonDecode(utf8.decode(res.bodyBytes))));
  }

  Future<Product360> generateDemoProduct({
    String preset = 'sneaker',
    int frameCount = 36,
  }) async {
    final res = await http.post(
      Uri.parse('$baseUrl/api/products/demo'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'preset': preset,
        'frame_count': frameCount,
        'ai_mode': 'auto',
      }),
    );
    if (res.statusCode != 200) {
      throw Exception('Failed to generate demo: ${res.body}');
    }
    return Product360.fromJson(
        Map<String, dynamic>.from(jsonDecode(utf8.decode(res.bodyBytes))));
  }

  Future<Product360> uploadMultiAngleImages({
    required String name,
    required String category,
    String description = '',
    required List<File> imageFiles,
  }) async {
    final req = http.MultipartRequest(
      'POST',
      Uri.parse('$baseUrl/api/products/capture-images'),
    );
    req.fields['name'] = name;
    req.fields['category'] = category;
    req.fields['description'] = description;
    req.fields['capture_mode'] = 'manual_gyro';
    req.fields['ai_mode'] = 'auto';

    for (final file in imageFiles) {
      req.files.add(await http.MultipartFile.fromPath('files', file.path));
    }

    final streamed = await req.send();
    final body = await streamed.stream.bytesToString();
    if (streamed.statusCode != 200) {
      throw Exception('Upload images failed: $body');
    }
    return Product360.fromJson(Map<String, dynamic>.from(jsonDecode(body)));
  }

  Future<Product360> uploadTurntableVideo({
    required String name,
    required String category,
    String description = '',
    required int targetFrames,
    required File videoFile,
  }) async {
    final req = http.MultipartRequest(
      'POST',
      Uri.parse('$baseUrl/api/products/capture-video'),
    );
    req.fields['name'] = name;
    req.fields['category'] = category;
    req.fields['description'] = description;
    req.fields['target_frames'] = targetFrames.toString();
    req.fields['ai_mode'] = 'auto';
    req.files.add(await http.MultipartFile.fromPath('video', videoFile.path));

    final streamed = await req.send();
    final body = await streamed.stream.bytesToString();
    if (streamed.statusCode != 200) {
      throw Exception('Upload video failed: $body');
    }
    return Product360.fromJson(Map<String, dynamic>.from(jsonDecode(body)));
  }

  Future<Product360> addHotspot({
    required String productId,
    required int frameIndex,
    required double x,
    required double y,
    required String title,
    String description = '',
    String tagType = 'detail',
  }) async {
    final res = await http.post(
      Uri.parse('$baseUrl/api/products/$productId/hotspots'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'frame_index': frameIndex,
        'x': x,
        'y': y,
        'title': title,
        'description': description,
        'tag_type': tagType,
        'visible_range': 3,
      }),
    );
    if (res.statusCode != 200) {
      throw Exception('Failed to add hotspot: ${res.body}');
    }
    return Product360.fromJson(
        Map<String, dynamic>.from(jsonDecode(utf8.decode(res.bodyBytes))));
  }

  Future<String> exportMp4({
    required String productId,
    String aspectRatio = '9:16',
    String bgTheme = 'studio_dark',
  }) async {
    final res = await http.post(
      Uri.parse('$baseUrl/api/products/$productId/export-mp4'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'aspect_ratio': aspectRatio,
        'bg_theme': bgTheme,
        'loops': 2,
        'fps': 24,
      }),
    );
    if (res.statusCode != 200) {
      throw Exception('Failed to export MP4: ${res.body}');
    }
    final data = jsonDecode(utf8.decode(res.bodyBytes));
    return resolveUrl(data['video_url'].toString());
  }
}
