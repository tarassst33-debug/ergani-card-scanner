import 'package:flutter/material.dart';

/// Chrome / Flutter Web — χρησιμοποίησε native app, όχι browser kiosk.
class WebGateScreen extends StatelessWidget {
  const WebGateScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Spacer(),
              Icon(
                Icons.phone_android,
                size: 72,
                color: Theme.of(context).colorScheme.primary,
              ),
              const SizedBox(height: 24),
              Text(
                'Ergani Card Scanner',
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),
              Text(
                'Η native εφαρμογή τρέχει σε Android και iOS.\n\n'
                'Για κινητό browser χρησιμοποίησε:\n'
                'http://<IP-Mac>:5050/\n\n'
                'Για Play Store / App Store build, άνοιξε το project '
                '`mobile/` στο Flutter.',
                style: Theme.of(context).textTheme.bodyLarge,
                textAlign: TextAlign.center,
              ),
              const Spacer(),
              FilledButton.icon(
                onPressed: () {},
                icon: const Icon(Icons.info_outline),
                label: const Text('Native app μόνο'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
