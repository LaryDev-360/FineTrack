# FineTrack — Backend API

API REST du projet **FineTrack** : backend Django 5.x + Django REST Framework (DRF), base PostgreSQL, authentification JWT. Conçu pour une application mobile **offline-first** avec synchronisation optionnelle.

Le cahier des charges prévoit **deux modes d’usage** :
- **Particulier** : suivi des dépenses/revenus, budgets, statistiques.
- **PME/Professionnel** : suivi des ventes, comptabilité simplifiée, génération de bilans et **score financier** (en phases post-MVP).

Le champ `user_type` dans `UserProfile` permet à l’app d’adapter l’interface et les écrans.

Les fonctionnalités spécifiques au mode **Professionnel/PME** (paiement QR, bilans financiers, scoring) sont prévues en phases post-MVP selon le cahier des charges.

---

## Stack

| Composant | Technologie |
|-----------|-------------|
| Framework | Django 5.x |
| API | Django REST Framework (DRF) |
| Langage | Python 3.10+ |
| Base de données | PostgreSQL |
| Authentification | JWT (djangorestframework-simplejwt) |
| Déploiement | Docker / Docker Compose (recommandé) |

---

## Prérequis

- **Python** 3.10 ou supérieur  
- **PostgreSQL** 12+ (ou instance distante)  
- **pip** et **venv** (ou Poetry)

---

## Installation

### 1. Environnement virtuel

```bash
cd backend
python3 -m venv venv
source venv/bin/activate   # Linux/macOS
# venv\Scripts\activate   # Windows
```

### 2. Dépendances

```bash
pip install -r requirements.txt
```

### 3. Variables d'environnement

Créer un fichier `.env` à la racine de `backend/` (voir `.env.example`) :

```env
SECRET_KEY=votre-secret-key-django
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgres://user:password@localhost:5432/finetrack_db
CORS_ALLOWED_ORIGINS=http://localhost:*
```

### 4. Base de données

**Toujours activer le venv avant d’exécuter `manage.py` :**

```bash
source venv/bin/activate   # Linux/macOS (depuis backend/)
python manage.py migrate
```

### 5. Lancer le serveur

```bash
source venv/bin/activate
python manage.py runserver
```

L’API est disponible sur **http://127.0.0.1:8000/** (ou le port configuré).

### Documentation API (Swagger / OpenAPI 3)

| URL | Description |
|-----|--------------|
| **http://127.0.0.1:8000/api/docs/** | Swagger UI — tester les endpoints et s’authentifier avec un JWT |
| **http://127.0.0.1:8000/api/redoc/** | ReDoc — lecture de la doc |
| **http://127.0.0.1:8000/api/schema/** | Schéma OpenAPI 3 (JSON) |

Dans Swagger UI : cliquer sur **Authorize**, puis renseigner le token JWT (champ **access** retourné par `POST /api/auth/login/`) au format `Bearer <access_token>` ou simplement coller l’access token.

---

## Structure du projet (backend)

```
backend/
├── manage.py
├── requirements.txt
├── .env.example
├── .env                 # (ignoré par git)
├── README.md            # ce fichier
├── config/              # projet Django (settings, urls, wsgi)
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   ├── accounts/        # User, UserProfile, auth JWT
│   ├── core/            # Comptes (Account), transferts
│   ├── categories/      # Catégories
│   ├── transactions/    # Transactions, bulk-sync
│   ├── budgets/         # Budgets
│   ├── statistics/      # Résumés, par catégorie, tendances
│   ├── accounting/    # Comptabilité automatisée, bilans, KPIs, export bilans
│   ├── export/          # Export CSV / JSON
│   └── payments/        # Paiements QR (intents, confirmation)
└── tests/
```

*(La structure réelle pourra être ajustée selon l’organisation des apps Django.)*

---

## Comptabilité et bilans (cahier des charges §6–7)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/api/accounting/period/` | Instantané pour une période : `granularity` = `day`, `week`, `month` ou `year` ; `reference_date` optionnel |
| GET | `/api/accounting/bilans/` | Série de bilans : `granularity` = `daily`, `weekly`, `monthly` ou `annual` ; `start_date`, `end_date` |
| GET | `/api/accounting/kpis/` | Indicateurs (ticket moyen, croissance CA, variabilité des revenus, etc.) sur une plage |
| GET | `/api/accounting/export/csv/` | Export CSV de la même série que `bilans/` |

Les montants **chiffre d’affaires** = somme des transactions **income** ; **dépenses** = **expense** ; les **transferts** sont exclus des totaux mais comptés dans `nombre_transactions` pour les vues qui agrègent « toutes opérations hors transfert » selon l’endpoint.

---

## Synchronisation offline (Phase 6)

- **Pull initial** : `GET /api/sync/initial/` charge tout le jeu de données utilisateur (profil, comptes, catégories, transactions, budgets, wallets).
- **Push par lot** : `POST …/bulk-sync/` sur **comptes**, **catégories**, **budgets** et **transactions** accepte des tableaux d’objets avec `client_id` / `local_id` optionnels, `id` serveur pour les mises à jour, et `client_up dated_at` (ISO 8601) pour la détection de conflits. Chaque réponse inclut `results` (statut par ligne : `created`, `updated`, `error`, `conflict`) et un **`summary`** (compteurs).
- **Throttling** (par adresse IP sur les endpoints **sans** JWT) : limites configurables dans `config/settings.py` (`REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`) pour `register`, `login`, `password_reset`, `refresh`. En cas de dépassement : HTTP **429** avec détails DRF.
- **Production** : définir `DEBUG=False`, `SECRET_KEY`, `ALLOWED_HOSTS`, `DATABASE_URL` (PostgreSQL). Fichier d’exemple : `docker-compose.prod.yml` (service PostgreSQL ; l’app peut tourner sur l’hôte ou un PaaS avec Gunicorn derrière un reverse proxy HTTPS).

---

## Modèles de données

### User & UserProfile

- **User** : modèle Django (email/password ou téléphone selon implémentation).
- **UserProfile** : `user_type` (`individual` = Particulier, `professional` = PME/Professionnel), `phone_number`, `country`, `default_currency` (ex. `XOF`), `language` (`fr`/`en`), `created_at`, `updated_at`.

### Account (comptes / portefeuilles)

- **Types** : `cash`, `bank`, `mobile_money`, `savings`, `other`.
- **Champs** : `user`, `name`, `account_type`, `initial_balance`, `current_balance`, `currency`, `color`, `icon`, `is_active`, timestamps.

### Category

- **Types** : `expense`, `income`.
- **Champs** : `user`, `name`, `category_type`, `color`, `icon`, `is_default`, timestamps.

### Transaction

- **Types** : `expense`, `income`, `transfer`.
- **Champs** : `user`, `transaction_type`, `amount`, `account`, `category` (nullable), `to_account` (pour transferts), `date`, `note`, `is_synced`, timestamps.

### Budget

- **Champs** : `user`, `category` (nullable pour budget global), `amount`, `period_start`, `period_end`, `is_global`, timestamps.

---

## API — Endpoints

Base URL : `/api/`

### Authentification

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/api/auth/register/` | Création de compte |
| POST | `/api/auth/login/` | Connexion (retourne JWT) |
| POST | `/api/auth/refresh/` | Rafraîchissement du token JWT |
| GET  | `/api/auth/profile/` | Récupération du profil |
| PUT  | `/api/auth/profile/` | Mise à jour du profil |
| POST | `/api/auth/password-reset/` | **Mot de passe oublié** — envoi d’un OTP par email |
| POST | `/api/auth/password-reset/verify/` | **Vérifier** un code OTP (valide / expiré) |
| POST | `/api/auth/password-reset/confirm/` | **Confirmer** avec OTP + nouveau mot de passe |
| POST | `/api/auth/password/change/` | **Changer le mot de passe** (JWT requis) |

À noter :
- `POST /api/auth/register/` accepte aussi un champ optionnel `user_type` : `individual` ou `professional`.
- Le token JWT renvoyé au login inclut `user_type` en plus de l’email.

### Comptes (Accounts)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET    | `/api/accounts/` | Liste des comptes |
| POST   | `/api/accounts/` | Création d’un compte |
| GET    | `/api/accounts/{id}/` | Détails d’un compte |
| PUT    | `/api/accounts/{id}/` | Mise à jour |
| DELETE | `/api/accounts/{id}/` | Suppression |
| POST   | `/api/accounts/transfer/` | Transfert entre deux comptes |
| POST   | `/api/accounts/bulk-sync/` | Synchronisation groupée des comptes (offline → cloud) |

### Catégories (Categories)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET    | `/api/categories/` | Liste |
| POST   | `/api/categories/` | Création |
| GET    | `/api/categories/{id}/` | Détails |
| PUT    | `/api/categories/{id}/` | Mise à jour |
| DELETE | `/api/categories/{id}/` | Suppression |
| POST   | `/api/categories/bulk-sync/` | Synchronisation groupée des catégories |

### Transactions

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET    | `/api/transactions/` | Liste (filtres : date, type, catégorie, compte) |
| POST   | `/api/transactions/` | Création |
| GET    | `/api/transactions/{id}/` | Détails |
| PUT    | `/api/transactions/{id}/` | Mise à jour |
| DELETE | `/api/transactions/{id}/` | Suppression |
| POST   | `/api/transactions/bulk-sync/` | Synchronisation en batch (offline → cloud) ; réponse avec `summary` |

### Budgets

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET    | `/api/budgets/` | Liste des budgets actifs |
| POST   | `/api/budgets/` | Création |
| GET    | `/api/budgets/{id}/` | Détails |
| PUT    | `/api/budgets/{id}/` | Mise à jour |
| DELETE | `/api/budgets/{id}/` | Suppression |
| POST   | `/api/budgets/bulk-sync/` | Synchronisation groupée des budgets |

### Statistiques

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/api/statistics/summary/` | Résumé dépenses/revenus (params : `start_date`, `end_date`) |
| GET | `/api/statistics/by-category/` | Répartition des dépenses par catégorie |
| GET | `/api/statistics/trends/` | Évolution sur plusieurs périodes |

### Export

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/api/export/csv/` | Export des transactions en CSV |
| GET | `/api/export/json/` | Export complet des données en JSON |

### Paiements QR (comptes professionnels)

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET  | `/api/merchant/me/` | Profil marchand : `merchant_id`, `payload_for_qr_static` (QR statique) |
| POST | `/api/payments/intents/` | Créer un intent (montant, compte à créditer) → payload pour QR dynamique |
| GET  | `/api/payments/intents/<uuid>/` | Détail d’un intent (client qui a scanné) |
| POST | `/api/payments/confirm/` | Confirmer le paiement (payer_account_id + payment_intent_id) |

**Flux** : (1) Marchand professionnel appelle `GET /api/merchant/me/` pour obtenir son `merchant_id` (QR statique) ou `POST /api/payments/intents/` pour un QR dynamique (montant + compte). (2) Client scanne le QR (payload `finetrack://pay/d/<uuid>`). (3) App client appelle `GET /api/payments/intents/<uuid>/` pour afficher montant et marchand. (4) Client confirme avec `POST /api/payments/confirm/` → débit du compte du client, crédit du compte du marchand, création des transactions.

---

## Authentification JWT

- **Login** : `POST /api/auth/login/` avec `email` + `password` (ou `phone` selon implémentation). Réponse : `access` + `refresh` tokens.
- **Requêtes authentifiées** : header `Authorization: Bearer <access_token>`.
- **Expiration** : access token court (ex. 15–30 min), refresh token plus long (ex. 7 jours).
- **Refresh** : `POST /api/auth/refresh/` avec `{"refresh": "<refresh_token>"}` pour obtenir un nouveau `access`.

### Mot de passe oublié (OTP) et changement de mot de passe

- **Mot de passe oublié** : `POST /api/auth/password-reset/` avec `{"email": "..."}` → un code OTP (6 chiffres) est envoyé par email (valide 15 min). Optionnel : `POST /api/auth/password-reset/verify/` avec `{"email": "...", "otp": "123456"}` pour vérifier le code avant d’afficher l’écran « Nouveau mot de passe ». Puis `POST /api/auth/password-reset/confirm/` avec `{"email": "...", "otp": "123456", "new_password": "...", "new_password_confirm": "..."}` pour définir le nouveau mot de passe.
- **Changer le mot de passe** (utilisateur connecté) : `POST /api/auth/password/change/` avec `{"old_password": "...", "new_password": "...", "new_password_confirm": "..."}` (JWT requis).
- En dev, avec `EMAIL_BACKEND=console`, l’OTP est affiché dans la console du serveur Django.

---

## Synchronisation offline-first

1. L’app mobile envoie les changements non synchronisés via **POST /api/transactions/bulk-sync/** (et endpoints dédiés pour comptes, catégories, budgets si besoin).
2. Le serveur valide, enregistre et renvoie les IDs serveur.
3. Connexion depuis un nouvel appareil : l’app fait un **pull** initial (GET accounts, categories, transactions, budgets) puis continue en sync bidirectionnelle selon la stratégie retenue (MVP : last write wins).

---

## Sécurité

- **HTTPS** obligatoire en production.
- **Mots de passe** : hachage via Django (PBKDF2) ou Argon2/bcrypt.
- **CSRF** : protection Django activée pour les sessions.
- **CORS** : `CORS_ALLOWED_ORIGINS` configuré pour l’app mobile / web autorisée.
- **Rate limiting** : recommandé sur `login`, `register`, `password-reset` (ex. `django-ratelimit`).
- **Validation** : sérialiseurs DRF pour toutes les entrées ; pas d’exposition directe de requêtes SQL brutes.

---

## Commandes utiles

Activer le venv avant toute commande `manage.py` : `source venv/bin/activate` (Linux/macOS).

```bash
source venv/bin/activate

# Migrations
python manage.py makemigrations
python manage.py migrate

# Superutilisateur (admin Django)
python manage.py createsuperuser

# Shell Django
python manage.py shell

# Tests
python manage.py test
```

---

## Docker (optionnel)

Exemple de démarrage avec Docker Compose (à adapter selon les fichiers présents) :

```bash
docker compose up -d
```

Prévoir un `Dockerfile` pour l’app Django et un `docker-compose.yml` avec services `db` (PostgreSQL) et `web` (Django). Les variables d’environnement peuvent être passées via `.env` ou `environment` dans `docker-compose.yml`.

---

## Ressources

- [Django](https://www.djangoproject.com/)
- [Django REST Framework](https://www.django-rest-framework.org/)
- [djangorestframework-simplejwt](https://github.com/jazzband/djangorestframework-simplejwt)
- [PostgreSQL](https://www.postgresql.org/)

---

*Backend FineTrack — Documentation alignée sur le cahier des charges (MVP).*
