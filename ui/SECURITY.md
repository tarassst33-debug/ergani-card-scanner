# Ασφάλεια Ergani UI

## Τι κάνει η εφαρμογή

- **Όλα τα δεδομένα** (χρήστες, εταιρείες, κωδικοί Ergani) μόνο στο **Firestore**, μέσω server (Admin SDK).
- **Κανείς από browser** δεν διαβάζει Firestore — ανέβασε τους κανόνες `firestore.rules` (όλα `false`).
- **Κωδικοί Ergani** κρυπτογραφημένοι (Fernet) με σταθερό `ERGANI_UI_SECRET`.
- **Δεν αποθηκεύονται** κωδικοί Ergani στο cookie/session — μόνο `company_id`.
- **Χωρίς** προεπιλεγμένο `admin123` — ισχυρός κωδικός μόνο από env.
- **Rate limit** στο login (8 προσπάθειες / 5 λεπτά ανά IP).
- Server **μόνο localhost** (`127.0.0.1`) από προεπιλογή.
- Χειροκίνητη σύνδεση Ergani (panel) **κλειστή** — μόνο login → εταιρεία.

## Ρύθμιση μόνο για εσένα

```bash
# Υποχρεωτικό — ίδιο πάντα
export ERGANI_UI_SECRET="$(openssl rand -hex 32)"

# Μόνο εσύ μπορείς να συνδεθείς (όνομα όπως στη Firestore)
export ERGANI_UI_ALLOWED_USERS="Δημητρης"

# Firebase credentials εκτός project
export ERGANI_FIREBASE_CREDENTIALS="$HOME/secrets/ergani-firebase.json"
```

Αντίγραψε `ui/.env.example` → `.env` (το `.env` είναι στο `.gitignore`).

## Κώδικας / repository

- Κάνε το repo **Private** στο GitHub/GitLab.
- **Μην ανεβάζεις** service account JSON, `.env`, κωδικούς.
- Μην μοιράζεις το `ERGANI_UI_SECRET` — αν αλλάξει, χάνονται οι κρυπτογραφημένοι κωδικοί Ergani στη βάση.

## Firebase Console

1. Firestore → **Rules** → deploy το `firestore.rules` του project.
2. Μόνο ο server με service account έχει πρόσβαση.

## Παραγωγή / internet

Αν το βγάλεις στο internet: HTTPS, `ERGANI_UI_HTTPS=1`, reverse proxy, ισχυροί κωδικοί, και περιορισμός `ERGANI_UI_ALLOWED_USERS`.
