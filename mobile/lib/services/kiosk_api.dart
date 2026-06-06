import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import 'device_storage.dart';

class KioskApiException implements Exception {
  KioskApiException(this.message);
  final String message;

  @override
  String toString() => message;
}

class KioskCompany {
  KioskCompany({required this.id, required this.name});

  final int id;
  final String name;

  factory KioskCompany.fromJson(Map<String, dynamic> json) {
    return KioskCompany(
      id: json['id'] as int? ?? 0,
      name: json['name'] as String? ?? '',
    );
  }
}

class KioskConfig {
  KioskConfig({
    required this.companyId,
    required this.companyName,
    required this.employerAfm,
    required this.branchNumber,
    this.syncedAtLabel = '',
  });

  final int companyId;
  final String companyName;
  final String employerAfm;
  final int branchNumber;
  final String syncedAtLabel;

  factory KioskConfig.fromJson(Map<String, dynamic> json) {
    return KioskConfig(
      companyId: json['company_id'] as int? ?? 0,
      companyName: json['company_name'] as String? ?? '',
      employerAfm: json['employer_afm'] as String? ?? '',
      branchNumber: json['branch_number'] as int? ?? 0,
      syncedAtLabel: json['synced_at_label'] as String? ?? '',
    );
  }
}

class PunchPreview {
  PunchPreview({
    required this.movementLabel,
    required this.afm,
    required this.displayName,
    required this.companyName,
    required this.canSubmit,
    this.warning = '',
  });

  final String movementLabel;
  final String? afm;
  final String displayName;
  final String companyName;
  final bool canSubmit;
  final String warning;

  factory PunchPreview.fromJson(Map<String, dynamic> json) {
    final employee = json['employee'] as Map<String, dynamic>?;
    final name = employee == null
        ? ''
        : '${employee['last_name'] ?? ''} ${employee['first_name'] ?? ''}'.trim();
    final afm = json['afm'] as String?;
    return PunchPreview(
      movementLabel: json['movement_label'] as String? ?? '',
      afm: afm,
      displayName: name.isNotEmpty ? name : (employee?['display_name'] as String? ?? ''),
      companyName: json['company_name'] as String? ?? '',
      canSubmit: afm != null && afm.isNotEmpty,
      warning: afm == null || afm.isEmpty
          ? 'Δεν αναγνωρίστηκε ΑΦΜ στο QR'
          : (employee == null ? 'Δεν βρέθηκε στη λίστα — κάνε Sync' : ''),
    );
  }
}

class PunchResult {
  PunchResult({
    required this.movementLabel,
    required this.displayName,
    required this.protocol,
  });

  final String movementLabel;
  final String displayName;
  final String? protocol;

  factory PunchResult.fromJson(Map<String, dynamic> json) {
    final employee = json['employee'] as Map<String, dynamic>? ?? {};
    return PunchResult(
      movementLabel: json['movement_label'] as String? ?? '',
      displayName: employee['display_name'] as String? ?? '',
      protocol: json['protocol'] as String?,
    );
  }
}

class PunchStatement {
  PunchStatement({
    required this.movementLabel,
    required this.fullName,
    required this.date,
    required this.time,
    required this.isArrival,
  });

  final String movementLabel;
  final String fullName;
  final String date;
  final String time;
  final bool isArrival;

  factory PunchStatement.fromJson(Map<String, dynamic> json) {
    final type = json['movement_type'] as String? ?? '';
    return PunchStatement(
      movementLabel: json['movement_label'] as String? ??
          (type == 'ARRIVAL' ? 'Check-in' : 'Check-out'),
      fullName: json['full_name'] as String? ?? '',
      date: (json['reference_date'] ?? json['movement_date'] ?? '') as String,
      time: json['movement_time'] as String? ?? '',
      isArrival: type == 'ARRIVAL',
    );
  }
}

class KioskApi {
  KioskApi({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;

  Future<Map<String, String>> _headers({int? companyId}) async {
    final cid = companyId ?? await DeviceStorage.getCompanyId();
    return {
      'Content-Type': 'application/json',
      if (AppConfig.kioskKey.isNotEmpty) 'X-Kiosk-Key': AppConfig.kioskKey,
      if (cid != null && cid > 0) 'X-Kiosk-Company-Id': '$cid',
    };
  }

  Uri _uri(String path) => Uri.parse('${AppConfig.normalizedApiBase()}$path');

  Future<List<KioskCompany>> fetchCompanies() async {
    final response = await _client.get(
      _uri('/api/kiosk/companies'),
      headers: await _headers(companyId: null),
    );
    if (response.statusCode >= 200 && response.statusCode < 300) {
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      final list = data['companies'] as List<dynamic>? ?? [];
      return list
          .map((e) => KioskCompany.fromJson(e as Map<String, dynamic>))
          .where((c) => c.id > 0)
          .toList();
    }
    throw KioskApiException(_errorMessage(response));
  }

  Future<KioskConfig> connect(int companyId) async {
    final response = await _client.post(
      _uri('/api/kiosk/connect'),
      headers: await _headers(companyId: companyId),
      body: jsonEncode({'company_id': companyId}),
    );
    return _decodeConfig(response);
  }

  Future<KioskConfig> fetchConfig() async {
    final response = await _client.get(
      _uri('/api/kiosk/config'),
      headers: await _headers(),
    );
    return _decodeConfig(response);
  }

  Future<PunchPreview> preview({
    required String movementType,
    required String qrPayload,
  }) async {
    final response = await _client.post(
      _uri('/api/kiosk/preview'),
      headers: await _headers(),
      body: jsonEncode({
        'movement_type': movementType,
        'qr_payload': qrPayload,
      }),
    );
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return PunchPreview.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      );
    }
    throw KioskApiException(_errorMessage(response));
  }

  Future<PunchResult> punch({
    required String movementType,
    required String qrPayload,
    String? employerAfm,
    int? branchNumber,
  }) async {
    final body = <String, dynamic>{
      'movement_type': movementType,
      'qr_payload': qrPayload,
    };
    if (employerAfm != null && employerAfm.isNotEmpty) {
      body['employer_afm'] = employerAfm;
    }
    if (branchNumber != null) {
      body['branch_number'] = branchNumber;
    }
    final response = await _client.post(
      _uri('/api/kiosk/punch'),
      headers: await _headers(),
      body: jsonEncode(body),
    );
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return PunchResult.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      );
    }
    throw KioskApiException(_errorMessage(response));
  }

  Future<int> syncPersonnel() async {
    final companyId = await DeviceStorage.getCompanyId();
    final response = await _client.post(
      _uri('/api/kiosk/sync'),
      headers: await _headers(),
      body: jsonEncode({'company_id': companyId}),
    );
    if (response.statusCode >= 200 && response.statusCode < 300) {
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      return data['count'] as int? ?? 0;
    }
    throw KioskApiException(_errorMessage(response));
  }

  Future<List<PunchStatement>> fetchStatements() async {
    final response = await _client.get(
      _uri('/api/kiosk/statements'),
      headers: await _headers(),
    );
    if (response.statusCode >= 200 && response.statusCode < 300) {
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      final list = data['punches'] as List<dynamic>? ?? [];
      return list
          .map((e) => PunchStatement.fromJson(e as Map<String, dynamic>))
          .toList();
    }
    throw KioskApiException(_errorMessage(response));
  }

  Future<bool> ping() async {
    final response = await _client.get(
      _uri('/api/kiosk/ping'),
      headers: await _headers(companyId: null),
    );
    return response.statusCode >= 200 && response.statusCode < 300;
  }

  KioskConfig _decodeConfig(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return KioskConfig.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      );
    }
    throw KioskApiException(_errorMessage(response));
  }

  String _errorMessage(http.Response response) {
    try {
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      final err = data['error'];
      if (err is String && err.isNotEmpty) return err;
    } catch (_) {
      /* ignore */
    }
    if (response.statusCode == 404) {
      return 'Παλιό server — κάνε restart το ui/app.py στη θύρα 5050.';
    }
    return 'Σφάλμα server (${response.statusCode})';
  }
}
