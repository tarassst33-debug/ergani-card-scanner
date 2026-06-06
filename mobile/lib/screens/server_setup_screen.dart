import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../services/device_storage.dart';
import '../services/kiosk_api.dart';
import 'company_setup_screen.dart';

/// Πρώτη ρύθμιση server (IP Mac + kiosk key από ui/.env).
class ServerSetupScreen extends StatefulWidget {
  const ServerSetupScreen({super.key});

  @override
  State<ServerSetupScreen> createState() => _ServerSetupScreenState();
}

class _ServerSetupScreenState extends State<ServerSetupScreen> {
  final _baseCtrl = TextEditingController(text: 'http://192.168.2.8:5050');
  final _keyCtrl = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _baseCtrl.dispose();
    _keyCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final base = _baseCtrl.text.trim();
    final key = _keyCtrl.text.trim();
    if (base.isEmpty || key.length < 16) {
      setState(() => _error = 'Συμπλήρωσε URL server και κλειδί (ERGANI_KIOSK_DEVICE_KEY).');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    await DeviceStorage.saveServer(apiBase: base, kioskKey: key);
    await AppConfig.hydrate();
    try {
      final ok = await KioskApi().ping();
      if (!ok) throw KioskApiException('Server δεν απάντησε.');
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const CompanySetupScreen()),
      );
    } on KioskApiException catch (e) {
      setState(() => _error = e.message);
    } catch (e) {
      setState(() => _error = 'Δεν συνδέθηκε: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Ρύθμιση server')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Text(
              'Σύνδεση με Mac / server',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            const Text(
              'Ίδιο Wi‑Fi με τον υπολογιστή. Το κλειδί είναι στο ui/.env '
              '(ERGANI_KIOSK_DEVICE_KEY).',
            ),
            const SizedBox(height: 20),
            TextField(
              controller: _baseCtrl,
              decoration: const InputDecoration(
                labelText: 'Διεύθυνση server',
                hintText: 'http://192.168.2.8:5050',
                border: OutlineInputBorder(),
              ),
              keyboardType: TextInputType.url,
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _keyCtrl,
              decoration: const InputDecoration(
                labelText: 'Kiosk κλειδί',
                border: OutlineInputBorder(),
              ),
              obscureText: true,
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ],
            const SizedBox(height: 24),
            FilledButton(
              onPressed: _busy ? null : _save,
              child: _busy
                  ? const SizedBox(
                      height: 22,
                      width: 22,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Αποθήκευση & συνέχεια'),
            ),
          ],
        ),
      ),
    );
  }
}
