# Firebase (Firestore) — projectcar-7846b

Όλα τα δεδομένα της εφαρμογής αποθηκεύονται στο **Firestore** μέσω του Flask server (Admin SDK).

## Collections

| Collection | Document ID | Περιεχόμενο |
|------------|-------------|-------------|
| `app_users` | `"1"`, `"2"`… | Λογαριασμοί (username, password_hash, role, company_ids) |
| `companies` | `"1"`, `"2"`… | Εταιρείες + κρυπτογραφημένοι κωδικοί Ergani |
| `shift_grids` | company id | Πρόγραμμα βαρέων (ψηφιακή κάρτα) ανά εταιρεία |
| `company_employees` | company id | Εργαζόμενοι: αφμ, όνομα, επώνυμο (συγχρονισμός από Ergani) |
| `submissions` | auto id | Ιστορικό υποβολών (π.χ. work card + πρωτόκολλο) |
| `meta/counters` | — | Τελευταία numeric id (users, companies) |
| `meta/schema` | — | Έκδοση schema / περιγραφή collections |

## Security rules

Το αρχείο `firestore.rules` **κλειδώνει** κάθε πρόσβαση από browser (mobile/web SDK). Μόνο ο server με **service account** διαβάζει/γράφει.

### Deploy rules + indexes

```bash
npm install -g firebase-tools
firebase login
cd /path/to/ergani-python-sdk-main
chmod +x ui/deploy-firestore.sh
./ui/deploy-firestore.sh
```

Ή:

```bash
firebase deploy --only firestore:rules,firestore:indexes
```

## Ρύθμιση server

```bash
export FIREBASE_PROJECT_ID=projectcar-7846b
export ERGANI_FIREBASE_CREDENTIALS="/path/to/ui/secrets/firebase-service-account.json"
export ERGANI_UI_SECRET="$(openssl rand -hex 32)"   # σταθερό
```

Αντίγραψε `ui/.env.example` → `ui/.env`.

## Έλεγχος σύνδεσης

```bash
PYTHONPATH=$PWD python3 ui/check_firebase.py
```

Στην εκκίνηση (`init_db`) δημιουργούνται αυτόματα τα έγγραφα `meta/counters` και `meta/schema` αν λείπουν.
