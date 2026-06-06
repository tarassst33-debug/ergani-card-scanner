# Ergani Card Scanner — Flutter (Android / iOS)

**Native εφαρμογή** για Check-in / Check-out με QR. Διαφορετική από το **Chrome** (`http://IP:5050/`), που είναι web kiosk + admin.

## Τι έχει η native app

- Ρύθμιση server (IP Mac + `ERGANI_KIOSK_DEVICE_KEY`)
- Επιλογή εταιρείας κάθε άνοιγμα
- Check-in / Check-out με κάμερα
- Επιβεβαίωση πριν την αποστολή στο Ergani
- Sync προσωπικού, Statements (μενού ☰)
- **Όχι admin** — admin μόνο από browser στο Mac

## Προαπαιτήσεις

- Flutter SDK 3.11+
- Server: `python3 ui/app.py` με `ui/.env` (ίδιο Wi‑Fi)

## Τρέξιμο (ανάπτυξη)

```bash
cd mobile
flutter pub get

# Android emulator / συσκευή — άλλαξε IP στο app ή:
flutter run \
  --dart-define=API_BASE=http://192.168.2.8:5050 \
  --dart-define=KIOSK_KEY=το-κλειδί-από-ui-env
```

Στην πρώτη εκκίνηση η εφαρμογή ζητά **URL** και **κλειδί** (αποθηκεύονται στη συσκευή).

## Build

```bash
# Android APK
flutter build apk --release \
  --dart-define=API_BASE=http://192.168.2.8:5050 \
  --dart-define=KIOSK_KEY=...

# iOS (Mac + Xcode)
flutter build ios --release \
  --dart-define=API_BASE=http://192.168.2.8:5050 \
  --dart-define=KIOSK_KEY=...
```

## Flutter Web

`flutter run -d chrome` δείχνει μήνυμα να χρησιμοποιήσεις **Android/iOS** — το web kiosk είναι το `ui/static` στο Flask.

## Δομή

| Web (Chrome) | Native (Flutter) |
|--------------|------------------|
| `http://IP:5050/` | `ergani_card_scanner` app |
| Kiosk scanner + 5× admin | Μόνο scanner |
| `localStorage` εταιρεία | `SharedPreferences` |
| html5-qrcode | `mobile_scanner` |
