# Firebase credentials (μην ανεβάσεις στο git)

1. [Firebase Console](https://console.firebase.google.com/project/projectcar-7846b/settings/serviceaccounts/adminsdk) → **Service accounts** → **Generate new private key**.
2. Αποθήκευσε το JSON εδώ ως:

   `firebase-service-account.json`

3. Εκκίνηση: `./ui/run.sh` (διαβάζει αυτόματα το αρχείο).
