import 'package:flutter/material.dart';

import '../services/device_storage.dart';
import '../services/kiosk_api.dart';
import 'punch_screen.dart';

/// Επιλογή εταιρείας — κάθε άνοιγμα εφαρμογής (native).
class CompanySetupScreen extends StatefulWidget {
  const CompanySetupScreen({super.key});

  @override
  State<CompanySetupScreen> createState() => _CompanySetupScreenState();
}

class _CompanySetupScreenState extends State<CompanySetupScreen> {
  final KioskApi _api = KioskApi();
  List<KioskCompany> _companies = [];
  int? _selectedId;
  bool _loading = true;
  bool _connecting = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final list = await _api.fetchCompanies();
      final saved = await DeviceStorage.getCompanyId();
      if (!mounted) return;
      setState(() {
        _companies = list;
        _selectedId = saved != null && list.any((c) => c.id == saved)
            ? saved
            : (list.length == 1 ? list.first.id : null);
        _loading = false;
      });
    } on KioskApiException catch (e) {
      setState(() {
        _error = e.message;
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = '$e';
        _loading = false;
      });
    }
  }

  Future<void> _connect() async {
    final id = _selectedId;
    if (id == null) {
      setState(() => _error = 'Επίλεξε εταιρεία.');
      return;
    }
    setState(() {
      _connecting = true;
      _error = null;
    });
    try {
      await _api.connect(id);
      await DeviceStorage.saveCompanyId(id);
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const PunchScreen()),
      );
    } on KioskApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _connecting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F1419),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Ergani',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 32,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                'Σύνδεση εργοδότη',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.grey.shade400, fontSize: 15),
              ),
              const SizedBox(height: 28),
              const Text(
                'Εταιρεία',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'Διάλεξε εταιρεία — Check-in/out μόνο για αυτή.',
                style: TextStyle(color: Colors.grey.shade400, fontSize: 13),
              ),
              const SizedBox(height: 16),
              if (_loading)
                const Center(child: CircularProgressIndicator())
              else if (_companies.isEmpty)
                Text(
                  _error ?? 'Δεν υπάρχουν εταιρείες στο server.',
                  style: TextStyle(color: Colors.red.shade300),
                )
              else
                DropdownButtonFormField<int>(
                  initialValue: _selectedId,
                  dropdownColor: const Color(0xFF1A2332),
                  style: const TextStyle(color: Colors.white),
                  decoration: InputDecoration(
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8),
                      borderSide: const BorderSide(color: Color(0xFF3B82F6)),
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8),
                      borderSide: const BorderSide(color: Color(0xFF3B82F6)),
                    ),
                  ),
                  items: [
                    const DropdownMenuItem(
                      value: null,
                      child: Text('— Επιλογή εταιρείας —'),
                    ),
                    ..._companies.map(
                      (c) => DropdownMenuItem(
                        value: c.id,
                        child: Text(c.name.isNotEmpty ? c.name : 'Εταιρεία ${c.id}'),
                      ),
                    ),
                  ],
                  onChanged: (v) => setState(() => _selectedId = v),
                ),
              if (_error != null && !_loading) ...[
                const SizedBox(height: 12),
                Text(_error!, style: TextStyle(color: Colors.red.shade300)),
              ],
              const Spacer(),
              FilledButton(
                onPressed: _connecting || _selectedId == null ? null : _connect,
                style: FilledButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  backgroundColor: const Color(0xFF3B82F6),
                ),
                child: _connecting
                    ? const SizedBox(
                        height: 22,
                        width: 22,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Text(
                        'Συνέχεια στο Scanner',
                        style: TextStyle(fontSize: 16),
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
