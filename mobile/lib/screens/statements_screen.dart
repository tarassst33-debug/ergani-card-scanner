import 'package:flutter/material.dart';

import '../services/kiosk_api.dart';

class StatementsScreen extends StatefulWidget {
  const StatementsScreen({super.key});

  @override
  State<StatementsScreen> createState() => _StatementsScreenState();
}

class _StatementsScreenState extends State<StatementsScreen> {
  final KioskApi _api = KioskApi();
  List<PunchStatement> _items = [];
  bool _loading = true;
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
      final list = await _api.fetchStatements();
      if (!mounted) return;
      setState(() {
        _items = list;
        _loading = false;
      });
    } on KioskApiException catch (e) {
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Statements'),
        backgroundColor: const Color(0xFF1A2B4A),
        foregroundColor: Colors.white,
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text(_error!))
              : _items.isEmpty
                  ? const Center(child: Text('Δεν υπάρχουν χτυπήματα.'))
                  : ListView.builder(
                      itemCount: _items.length,
                      itemBuilder: (context, i) {
                        final p = _items[i];
                        return ListTile(
                          leading: Icon(
                            p.isArrival ? Icons.login : Icons.logout,
                            color: p.isArrival ? Colors.green : Colors.orange,
                          ),
                          title: Text(p.fullName.isNotEmpty ? p.fullName : '—'),
                          subtitle: Text('${p.date} ${p.time}'),
                          trailing: Text(
                            p.movementLabel,
                            style: const TextStyle(fontWeight: FontWeight.w600),
                          ),
                        );
                      },
                    ),
    );
  }
}
