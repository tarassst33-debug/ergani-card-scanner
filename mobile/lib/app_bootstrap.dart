import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'config/app_config.dart';
import 'screens/company_setup_screen.dart';
import 'screens/punch_screen.dart';
import 'screens/server_setup_screen.dart';
import 'screens/web_gate_screen.dart';
import 'services/device_storage.dart';

/// Επιλογή αρχικής οθόνης: Web ≠ Native.
class AppBootstrap extends StatefulWidget {
  const AppBootstrap({super.key});

  @override
  State<AppBootstrap> createState() => _AppBootstrapState();
}

class _AppBootstrapState extends State<AppBootstrap> {
  Widget? _home;

  @override
  void initState() {
    super.initState();
    _resolveHome();
  }

  Future<void> _resolveHome() async {
    if (kIsWeb) {
      setState(() => _home = const WebGateScreen());
      return;
    }
    await AppConfig.hydrate();
    final hasServer = await DeviceStorage.hasServerConfig();
    if (!hasServer) {
      setState(() => _home = const ServerSetupScreen());
      return;
    }
    setState(() => _home = const CompanySetupScreen());
  }

  @override
  Widget build(BuildContext context) {
    if (_home == null) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }
    return _home!;
  }
}

/// Μετά login εταιρείας → scanner (χωρίς admin στο native).
class NativeAppRoutes {
  static Route<dynamic>? onGenerateRoute(RouteSettings settings) {
    switch (settings.name) {
      case '/scanner':
        return MaterialPageRoute(builder: (_) => const PunchScreen());
      case '/company':
        return MaterialPageRoute(builder: (_) => const CompanySetupScreen());
      default:
        return null;
    }
  }
}
