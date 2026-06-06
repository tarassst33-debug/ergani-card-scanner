import '../services/device_storage.dart';

/// Ρυθμίσεις API — dart-define ή αποθήκευση στη συσκευή (Settings στην εφαρμογή).
class AppConfig {
  static String apiBase = const String.fromEnvironment(
    'API_BASE',
    defaultValue: 'http://127.0.0.1:5050',
  );

  static String kioskKey = const String.fromEnvironment(
    'KIOSK_KEY',
    defaultValue: '',
  );

  static Future<void> hydrate() async {
    final storedBase = await DeviceStorage.getApiBase();
    final storedKey = await DeviceStorage.getKioskKey();
    if (storedBase != null && storedBase.isNotEmpty) {
      apiBase = storedBase;
    }
    if (storedKey != null && storedKey.isNotEmpty) {
      kioskKey = storedKey;
    }
  }

  static String normalizedApiBase() {
    var base = apiBase.trim();
    while (base.endsWith('/')) {
      base = base.substring(0, base.length - 1);
    }
    return base;
  }
}
