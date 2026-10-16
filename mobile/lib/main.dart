import 'package:flutter/material.dart';
import 'screens/home_screen.dart';
import 'services/api_client.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  final apiClient = Pocket3DApiClient(
    baseUrl: const String.fromEnvironment(
      'POCKET3D_API_URL',
      defaultValue: 'http://localhost:8000',
    ),
  );
  runApp(Pocket3DShowcaseApp(apiClient: apiClient));
}

class Pocket3DShowcaseApp extends StatelessWidget {
  final Pocket3DApiClient apiClient;

  const Pocket3DShowcaseApp({super.key, required this.apiClient});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Pocket 3D Showcase',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark(useMaterial3: true).copyWith(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF38BDF8),
          brightness: Brightness.dark,
        ),
      ),
      home: HomeScreen(apiClient: apiClient),
    );
  }
}
