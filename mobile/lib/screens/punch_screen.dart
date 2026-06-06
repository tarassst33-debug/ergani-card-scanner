import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../services/kiosk_api.dart';
import 'company_setup_screen.dart';
import 'punch_confirm_screen.dart';
import 'qr_scan_screen.dart';
import 'server_setup_screen.dart';
import 'statements_screen.dart';

/// Native scanner — Check-in / Check-out (διαφορετικό από Chrome UI).
class PunchScreen extends StatefulWidget {
  const PunchScreen({super.key});

  @override
  State<PunchScreen> createState() => _PunchScreenState();
}

class _PunchScreenState extends State<PunchScreen> {
  final KioskApi _api = KioskApi();
  final GlobalKey<ScaffoldState> _scaffoldKey = GlobalKey<ScaffoldState>();
  late Timer _clockTimer;
  DateTime _now = DateTime.now();
  KioskConfig? _config;
  String? _statusError;
  bool _loadingConfig = true;
  bool _syncing = false;

  static const Color _blue = Color(0xFF1E6FD9);
  static const Color _navy = Color(0xFF1A2B4A);
  static const Color _green = Color(0xFF22C55E);
  static const Color _orange = Color(0xFFF97316);

  @override
  void initState() {
    super.initState();
    _clockTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() => _now = DateTime.now());
    });
    _loadConfig();
  }

  @override
  void dispose() {
    _clockTimer.cancel();
    super.dispose();
  }

  Future<void> _loadConfig() async {
    setState(() {
      _loadingConfig = true;
      _statusError = null;
    });
    try {
      final config = await _api.fetchConfig();
      if (!mounted) return;
      setState(() {
        _config = config;
        _loadingConfig = false;
      });
    } on KioskApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _statusError = e.message;
        _loadingConfig = false;
      });
    }
  }

  Future<void> _sync() async {
    setState(() => _syncing = true);
    try {
      final n = await _api.syncPersonnel();
      await _loadConfig();
      if (!mounted) return;
      _showMessage('Sync OK — $n εργαζόμενοι');
    } on KioskApiException catch (e) {
      _showMessage(e.message, isError: true);
    } finally {
      if (mounted) setState(() => _syncing = false);
    }
  }

  Future<void> _changeCompany() async {
    await Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const CompanySetupScreen()),
    );
  }

  Future<void> _openScanner(String movementType, String title) async {
    if (_config == null) {
      _showMessage('Δεν έχει φορτωθεί η εταιρεία.', isError: true);
      return;
    }
    final qr = await Navigator.of(context).push<String>(
      MaterialPageRoute(builder: (_) => QrScanScreen(title: title)),
    );
    if (qr == null || !mounted) return;

    PunchPreview preview;
    try {
      preview = await _api.preview(movementType: movementType, qrPayload: qr);
    } on KioskApiException catch (e) {
      _showMessage(e.message, isError: true);
      return;
    }

    if (!mounted) return;
    final confirmed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => PunchConfirmScreen(
          preview: preview,
          movementType: movementType,
        ),
      ),
    );
    if (confirmed != true || !mounted) return;

    try {
      final result = await _api.punch(
        movementType: movementType,
        qrPayload: qr,
        employerAfm: _config!.employerAfm,
        branchNumber: _config!.branchNumber,
      );
      if (!mounted) return;
      _showMessage(
        '${result.movementLabel}\n${result.displayName}'
        '${result.protocol != null ? '\nΠρωτόκολλο: ${result.protocol}' : ''}',
      );
    } on KioskApiException catch (e) {
      _showMessage(e.message, isError: true);
    }
  }

  void _showMessage(String text, {bool isError = false}) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(text),
        backgroundColor: isError ? Colors.red.shade700 : Colors.green.shade700,
        duration: const Duration(seconds: 4),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final timeText = DateFormat('HH:mm').format(_now);
    final dayText = DateFormat('EEEE d/M', 'el_GR').format(_now);

    return Scaffold(
      key: _scaffoldKey,
      backgroundColor: const Color(0xFFF3F4F6),
      endDrawer: _buildDrawer(),
      appBar: AppBar(
        backgroundColor: Colors.white,
        foregroundColor: _navy,
        elevation: 0,
        title: Text(
          _config?.companyName ?? 'Ergani Scanner',
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.menu),
            onPressed: () => _scaffoldKey.currentState?.openEndDrawer(),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            if (_loadingConfig)
              const LinearProgressIndicator(minHeight: 2)
            else if (_statusError != null)
              Padding(
                padding: const EdgeInsets.all(12),
                child: Text(
                  _statusError!,
                  style: TextStyle(color: Colors.red.shade700, fontSize: 13),
                  textAlign: TextAlign.center,
                ),
              ),
            const SizedBox(height: 16),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 28),
              child: _PunchButton(
                label: 'Check-in',
                subtitle: 'Προσέλευση',
                color: _blue,
                accentColor: _green,
                onPressed: () => _openScanner('ARRIVAL', 'Προσέλευση'),
              ),
            ),
            const SizedBox(height: 20),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 28),
              child: _PunchButton(
                label: 'Check-out',
                subtitle: 'Αποχώρηση',
                color: _blue,
                accentColor: _orange,
                onPressed: () => _openScanner('DEPARTURE', 'Αποχώρηση'),
              ),
            ),
            const Spacer(),
            Text(
              timeText,
              style: const TextStyle(
                fontSize: 56,
                fontWeight: FontWeight.w800,
                color: _navy,
              ),
            ),
            Text(
              dayText,
              style: const TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w700,
                color: _navy,
              ),
            ),
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }

  Widget _buildDrawer() {
    final cfg = _config;
    return Drawer(
      child: SafeArea(
        child: ListView(
          padding: const EdgeInsets.symmetric(vertical: 8),
          children: [
            DrawerHeader(
              decoration: const BoxDecoration(color: Color(0xFF1E6FD9)),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Ergani Scanner',
                    style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    cfg?.companyName ?? '—',
                    style: const TextStyle(color: Colors.white70),
                  ),
                  if (cfg != null) ...[
                    const SizedBox(height: 4),
                    Text('VAT: ${cfg.employerAfm}', style: const TextStyle(color: Colors.white60, fontSize: 12)),
                  ],
                ],
              ),
            ),
            ListTile(
              leading: const Icon(Icons.sync),
              title: Text(_syncing ? 'Συγχρονισμός…' : 'Sync προσωπικού'),
              onTap: _syncing ? null : () {
                Navigator.pop(context);
                _sync();
              },
            ),
            ListTile(
              leading: const Icon(Icons.list),
              title: const Text('Statements'),
              onTap: () {
                Navigator.pop(context);
                Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const StatementsScreen()),
                );
              },
            ),
            ListTile(
              leading: const Icon(Icons.business),
              title: const Text('Αλλαγή εταιρείας'),
              onTap: () {
                Navigator.pop(context);
                _changeCompany();
              },
            ),
            ListTile(
              leading: const Icon(Icons.settings),
              title: const Text('Ρύθμιση server'),
              onTap: () {
                Navigator.pop(context);
                Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const ServerSetupScreen()),
                );
              },
            ),
            const Divider(),
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text(
                'Native app · Android / iOS\nΓια admin χρησιμοποίησε browser στο Mac.',
                style: TextStyle(fontSize: 12, color: Colors.grey),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PunchButton extends StatelessWidget {
  const _PunchButton({
    required this.label,
    required this.subtitle,
    required this.color,
    required this.accentColor,
    required this.onPressed,
  });

  final String label;
  final String subtitle;
  final Color color;
  final Color accentColor;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: color,
      borderRadius: BorderRadius.circular(14),
      elevation: 2,
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(14),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(vertical: 28),
          child: Column(
            children: [
              Text(
                label,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 28,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                subtitle,
                style: TextStyle(color: Colors.white.withValues(alpha: 0.85), fontSize: 14),
              ),
              const SizedBox(height: 14),
              Container(
                width: 120,
                height: 5,
                decoration: BoxDecoration(
                  color: accentColor,
                  borderRadius: BorderRadius.circular(3),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
