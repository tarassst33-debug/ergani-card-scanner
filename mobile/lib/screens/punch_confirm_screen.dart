import 'package:flutter/material.dart';

import '../services/kiosk_api.dart';

class PunchConfirmScreen extends StatelessWidget {
  const PunchConfirmScreen({
    super.key,
    required this.preview,
    required this.movementType,
  });

  final PunchPreview preview;
  final String movementType;

  @override
  Widget build(BuildContext context) {
    final isIn = movementType == 'ARRIVAL';
    return Scaffold(
      appBar: AppBar(
        title: const Text('Επιβεβαίωση'),
        backgroundColor: const Color(0xFF1A2B4A),
        foregroundColor: Colors.white,
      ),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              preview.movementLabel.isNotEmpty
                  ? preview.movementLabel
                  : (isIn ? 'Check-in · Προσέλευση' : 'Check-out · Αποχώρηση'),
              style: Theme.of(context).textTheme.titleLarge?.copyWith(
                    color: const Color(0xFF1E6FD9),
                    fontWeight: FontWeight.bold,
                  ),
            ),
            const SizedBox(height: 20),
            if (preview.companyName.isNotEmpty)
              _row('Εταιρεία', preview.companyName),
            _row('ΑΦΜ', preview.afm ?? '—'),
            if (preview.displayName.isNotEmpty)
              _row('Εργαζόμενος', preview.displayName),
            if (preview.warning.isNotEmpty) ...[
              const SizedBox(height: 16),
              Text(
                preview.warning,
                style: TextStyle(color: Colors.orange.shade800),
              ),
            ],
            const Spacer(),
            FilledButton(
              onPressed: preview.canSubmit
                  ? () => Navigator.of(context).pop(true)
                  : null,
              style: FilledButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 16),
                backgroundColor: Colors.green.shade700,
              ),
              child: const Text('Επιβεβαίωση & αποστολή Ergani'),
            ),
            const SizedBox(height: 10),
            OutlinedButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Άκυρο — ξανά σάρωση'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _row(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(color: Colors.grey, fontSize: 12)),
          Text(value, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w500)),
        ],
      ),
    );
  }
}
