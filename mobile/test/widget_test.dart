import 'package:ergani_card_scanner/main.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('App starts', (WidgetTester tester) async {
    await tester.pumpWidget(const ErganiCardScannerApp());
    await tester.pump();
    expect(find.byType(ErganiCardScannerApp), findsOneWidget);
  });
}
