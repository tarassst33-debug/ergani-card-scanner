import 'package:shared_preferences/shared_preferences.dart';

/// Τοπικές ρυθμίσεις συσκευής (server, κλειδί, εταιρεία).
class DeviceStorage {
  static const _apiBase = 'ergani_api_base';
  static const _kioskKey = 'ergani_kiosk_key';
  static const _companyId = 'ergani_kiosk_company_id';

  static Future<String?> getApiBase() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_apiBase);
  }

  static Future<String?> getKioskKey() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_kioskKey);
  }

  static Future<int?> getCompanyId() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getInt(_companyId);
  }

  static Future<void> saveServer({required String apiBase, required String kioskKey}) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_apiBase, apiBase.trim());
    await prefs.setString(_kioskKey, kioskKey.trim());
  }

  static Future<void> saveCompanyId(int id) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(_companyId, id);
  }

  static Future<void> clearCompany() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_companyId);
  }

  static Future<bool> hasServerConfig() async {
    final base = await getApiBase();
    final key = await getKioskKey();
    return (base ?? '').isNotEmpty && (key ?? '').length >= 16;
  }

  static Future<bool> hasCompany() async {
    final id = await getCompanyId();
    return id != null && id > 0;
  }
}
