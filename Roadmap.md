# Roadmap — Implémentation du Backend FineTrack

Plan d’implémentation du backend API (Django + DRF + PostgreSQL) pour FineTrack, aligné sur le cahier des charges et le README backend.

---

## Vue d’ensemble

| Phase | Objectif | Durée estimée |
|-------|----------|----------------|
| **Phase 0** | Setup projet, config, outillage | 2–3 jours |
| **Phase 1** | Auth (JWT) + modèles de base | 1 semaine |
| **Phase 2** | Comptes & catégories (CRUD + API) | 1 semaine |
| **Phase 3** | Transactions & transferts | 1–2 semaines |
| **Phase 4** | Budgets | 3–5 jours |
| **Phase 5** | Statistiques & export | 1 semaine |
| **Phase 6** | Bulk-sync, sécurité, polish | 1 semaine |
| **Phase 7** | Tests, doc, déploiement | 1 semaine |

**Total estimé (backend seul)** : ~6–8 semaines pour un MVP complet.

---

## Alignement avec le cahier des charges

Le document fourni décompose aussi les fonctionnalités en grandes phases :
- **Phase 1 (MVP)** : gestion des comptes, transactions, statistiques.
- **Phase 2** : **paiement via QR code** + enregistrement automatique des transactions.
- **Phase 3** : **bilans financiers** + **score de crédit**.
- **Phase 4** : intégration **mobile money** via API + partenariats.

Notre roadmap technique (0 à 7) inclut ces éléments, mais ajoute aussi les aspects “système” indispensables : auth JWT, offline-first, synchronisation, sécurité, tests et déploiement.

---

## Offline-first : rôle du backend

L’architecture **offline-first** repose sur deux briques :

| Côté | Rôle | Technologie |
|------|------|-------------|
| **Mobile (Flutter)** | Données en local, app utilisable sans réseau | **Hive** (NoSQL) ou **SQLite** (via `sqflite`) — base embarquée pour comptes, transactions, catégories, budgets |
| **Backend (ce projet)** | Source de vérité quand l’utilisateur est connecté ; synchronisation et multi‑appareils | **PostgreSQL** + API REST |

Le backend **ne gère pas** Hive ni SQLite : ceux-ci sont dans l’app mobile. Il doit en revanche :

- Exposer un **pull initial** (GET comptes, catégories, transactions, budgets) pour un nouvel appareil ou après réinstallation.
- Exposer **POST /api/transactions/bulk-sync/** (et équivalents si besoin pour comptes/catégories/budgets) pour que l’app envoie les changements faits hors ligne (stockés en local dans Hive/SQLite).
- Retourner les **IDs serveur** pour que le client marque les entrées comme synchronisées dans sa base locale.
- Gérer les conflits en MVP avec une stratégie simple (ex. **last write wins**).

Ce Roadmap planifie donc l’API qui permettra à l’app (Hive ou SQLite côté client) de rester offline-first tout en se synchronisant avec ce backend lorsqu’une connexion est disponible.

---

## Phase 0 — Setup et configuration

**Objectif** : Projet Django opérationnel, base de données, environnement de dev reproductible.

### Tâches

- [x] Créer le projet Django (`django-admin startproject config .`)
- [x] Configurer `config/settings.py` (env vars, PostgreSQL via `DATABASE_URL`, CORS, REST_FRAMEWORK)
- [x] Rédiger `requirements.txt` (Django 5.x, djangorestframework, djangorestframework-simplejwt, psycopg2-binary, python-dotenv, django-cors-headers, gunicorn)
- [x] Créer `.env.example` et documenter les variables (SECRET_KEY, DEBUG, ALLOWED_HOSTS, DATABASE_URL, CORS_ALLOWED_ORIGINS)
- [x] Créer la structure `apps/` et enregistrer les apps dans `INSTALLED_APPS`
- [ ] (Optionnel) Docker Compose : service `db` (PostgreSQL), service `web` (Django), `.env` pour la DB
- [x] Vérifier `python manage.py migrate` et `runserver`

### Livrables

- Projet Django qui démarre sans erreur
- Connexion PostgreSQL fonctionnelle
- `README.md` backend à jour si la structure change

---

## Phase 1 — Authentification et modèles de base

**Objectif** : Utilisateurs, profils, JWT ; modèles Account, Category, Transaction, Budget créés et migrés.

### Tâches

- [ ] **App `accounts`**
  - [ ] Modèle `UserProfile` (OneToOne User), champs : `phone_number`, `country`, `default_currency`, `language`, timestamps
  - [ ] Signal ou override pour créer un `UserProfile` à la création d’un User
  - [ ] Endpoints JWT : register, login, logout, refresh (Simple JWT)
  - [ ] Endpoints profil : GET/PUT `/api/auth/profile/` (sérialiseur User + UserProfile)
  - [ ] Endpoint password-reset (demande + token) si prévu pour le MVP
  - [ ] Validation mot de passe (longueur, complexité) côté API
- [ ] **Modèles métier (dans les apps dédiées ou `core`)**
  - [ ] `Account` : user, name, account_type, initial_balance, current_balance, currency, color, icon, is_active, timestamps
  - [ ] `Category` : user, name, category_type (expense/income), color, icon, is_default, timestamps
  - [ ] `Transaction` : user, transaction_type, amount, account, category (nullable), to_account (nullable), date, note, is_synced, timestamps
  - [ ] `Budget` : user, category (nullable), amount, period_start, period_end, is_global, timestamps
- [ ] Migrations initiales pour tous les modèles
- [ ] Permissions : tout est scoped par `user` (authenticated + owner)

### Livrables

- Inscription / connexion / refresh JWT opérationnels
- Profil utilisateur récupérable et modifiable
- Modèles Account, Category, Transaction, Budget en base avec migrations

---

## Phase 2 — Comptes et catégories

**Objectif** : API complète pour les comptes et les catégories (CRUD, listes filtrées par user).

### Tâches

- [ ] **App comptes (ex. `core` ou `accounts` dédiée aux comptes financiers)**
  - [ ] Sérialiseurs : AccountSerializer (liste + détail + création + mise à jour)
  - [ ] ViewSet ou APIViews : GET liste, POST, GET détail, PUT, DELETE
  - [ ] Filtrage : uniquement les comptes de l’utilisateur connecté
  - [ ] Endpoint `POST /api/accounts/transfer/` : transfert entre deux comptes (mise à jour des soldes + création des transactions ou logique métier définie)
- [ ] **App `categories`**
  - [ ] Sérialiseurs : CategorySerializer (CRUD)
  - [ ] ViewSet/APIViews : GET liste, POST, GET détail, PUT, DELETE
  - [ ] Catégories par défaut : fixture ou migration data pour catégories prédéfinies (optionnel, ou créées à la création du user)
- [ ] Enregistrement des routes dans `config/urls.py` (ex. `/api/accounts/`, `/api/categories/`)
- [ ] Tests manuels (Postman/curl) ou premiers tests unitaires

### Livrables

- CRUD comptes et catégories fonctionnel
- Transfert entre comptes implémenté (logique métier + impact sur les soldes)

---

## Phase 3 — Transactions

**Objectif** : Création, lecture, mise à jour, suppression des transactions ; mise à jour cohérente des soldes des comptes.

### Tâches

- [ ] **App `transactions`**
  - [ ] Sérialiseurs : TransactionSerializer (avec champs account, category, to_account selon le type)
  - [ ] Validation : cohérence type / catégorie / to_account (ex. transfert => to_account requis)
  - [ ] ViewSet/APIViews : GET liste (filtres : date, type, catégorie, compte), POST, GET détail, PUT, DELETE
  - [ ] Logique métier : à chaque création/modification/suppression de transaction, recalculer ou mettre à jour `current_balance` des comptes concernés
  - [ ] Gestion des transferts : deux lignes (sortie compte A, entrée compte B) ou une ligne avec to_account selon le modèle retenu
- [ ] Endpoint `POST /api/transactions/bulk-sync/`
  - [ ] Accepte un tableau de transactions (créations/mises à jour)
  - [ ] Validation et enregistrement en batch
  - [ ] Retour des IDs serveur pour que l’app mobile marque les entrées comme synchronisées
  - [ ] Stratégie conflits MVP : last write wins (par exemple via `updated_at` ou id client)
- [ ] Pagination sur la liste des transactions (taille de page raisonnable, ex. 50)
- [ ] Tests unitaires sur la logique de solde (création, modification, suppression, transfert)

### Livrables

- CRUD transactions opérationnel avec soldes à jour
- Bulk-sync utilisable par l’app mobile pour la synchronisation offline → cloud (données locales de l’app : Hive ou SQLite)

---

## Phase 4 — Budgets

**Objectif** : CRUD budgets (global et par catégorie), périodes (period_start, period_end).

### Tâches

- [ ] **App `budgets`**
  - [ ] Sérialiseurs : BudgetSerializer (category nullable pour budget global, is_global)
  - [ ] ViewSet/APIViews : GET liste (filtres : période, actifs), POST, GET détail, PUT, DELETE
  - [ ] Validation : period_start < period_end, pas de chevauchement si règle métier définie
  - [ ] Optionnel : endpoint ou champ dérivé « montant dépensé sur la période » pour affichage (sinon calcul côté client ou dans statistics)
- [ ] Routes : `/api/budgets/`
- [ ] Tests manuels ou unitaires

### Livrables

- API budgets prête pour l’app mobile (création, suivi par catégorie ou global)

---

## Phase 5 — Statistiques et export

**Objectif** : Endpoints de synthèse pour tableaux de bord et exports CSV/JSON.

### Tâches

- [ ] **App `statistics`**
  - [ ] `GET /api/statistics/summary/` : paramètres `start_date`, `end_date` ; retour : total dépenses, total revenus, solde net (et éventuellement solde total des comptes)
  - [ ] `GET /api/statistics/by-category/` : répartition des dépenses par catégorie (montants et/ou pourcentages) sur la période
  - [ ] `GET /api/statistics/trends/` : évolution sur plusieurs périodes (ex. par jour ou par mois) pour graphiques
- [ ] **App `export`**
  - [ ] `GET /api/export/csv/` : export des transactions (filtres optionnels : période, compte) en CSV
  - [ ] `GET /api/export/json/` : export complet (comptes, catégories, transactions, budgets) pour backup
- [ ] Sécurité : exports limités à l’utilisateur connecté, pas d’accès aux données des autres users
- [ ] Tests (au moins smoke tests sur les endpoints)

### Livrables

- Dashboard et graphiques alimentables côté mobile via les endpoints statistics
- Export CSV et JSON opérationnels pour sauvegarde et migration

---

## Phase 6 — Synchronisation, sécurité et polish

**Objectif** : Bulk-sync robuste, rate limiting, validation, documentation API.

### Tâches

- [x] **Bulk-sync**
  - [x] Gérer les créations et mises à jour dans un même batch (id client → id serveur dans la réponse)
  - [x] Gestion d’erreurs partielles (quelles entrées ont échoué, retour explicite)
  - [x] Optionnel : endpoint « pull » initial — `GET /api/sync/initial/`
  - [x] Bulk-sync également pour **comptes**, **catégories**, **budgets** ; champ **`summary`** sur toutes les réponses bulk
- [x] **Sécurité**
  - [x] Rate limiting sur login, register, password-reset, refresh (DRF, `config/throttles.py`)
  - [x] Validation renforcée (longueurs, montants, etc. sur les sérialiseurs principaux)
  - [x] Ressources scoped par utilisateur (querysets / permissions) — vérifié
- [x] **Documentation**
  - [x] Schéma OpenAPI / Swagger sous `/api/schema/`, `/api/docs/` (schémas Paiements QR complétés)
  - [x] README backend mis à jour (sync, throttling, prod)
- [x] **Config production**
  - [x] ALLOWED_HOSTS, DEBUG=False, SECRET_KEY via env (`settings.py`, `.env.example`)
  - [x] `docker-compose.prod.yml` (PostgreSQL) + notes Gunicorn / reverse proxy dans le README

### Livrables

- Bulk-sync fiable pour l’app mobile
- Rate limiting et validation en place
- Documentation API (Swagger/OpenAPI) disponible

---

## Cahier des charges PDF — comptabilité & bilans (§6–7)

Fonctionnalités implémentées côté API (`apps/accounting`) :

- [x] Suivi des flux, calculs par jour / semaine / mois / année (`GET /api/accounting/period/`)
- [x] Série de bilans sur une plage + export CSV (`GET /api/accounting/bilans/`, `GET /api/accounting/export/csv/`)
- [x] Indicateurs clés §6.3 (`GET /api/accounting/kpis/`)

Non couvert ici (autre périmètre / phase) :

- [ ] **Score financier** (§8 du PDF) — endpoint dédié à prévoir
- [ ] Export PDF des bilans (hors CSV)

---

## Phase 7 — Tests et déploiement

**Objectif** : Couverture de tests suffisante, CI, déploiement sur un environnement de staging/production.

### Tâches

- [ ] **Tests**
  - [ ] Tests unitaires modèles (contraintes, propriétés)
  - [ ] Tests API : auth (register, login, refresh), CRUD comptes, catégories, transactions, budgets
  - [ ] Tests logique métier : soldes après transaction/transfert, bulk-sync
  - [ ] Tests permissions : accès uniquement à ses propres données
- [ ] **CI**
  - [ ] GitHub Actions ou GitLab CI : lint (flake8/ruff), tests, migrations check
- [ ] **Déploiement**
  - [ ] Dockerfile pour l’app Django (multi-stage si besoin)
  - [ ] Docker Compose avec PostgreSQL + web (gunicorn)
  - [ ] Déploiement sur un cloud (Render, Railway, DigitalOcean, AWS, etc.) et vérification des variables d’environnement
- [ ] **Documentation**
  - [ ] Mise à jour du README backend (commandes de test, déploiement)
  - [ ] Ce Roadmap mis à jour (cocher les tâches réalisées, noter les écarts)

### Livrables

- Suite de tests exécutée en CI
- Backend déployé et accessible (staging au minimum)
- README et Roadmap à jour

---

## Dépendances entre phases

```
Phase 0 (Setup)
    ↓
Phase 1 (Auth + Modèles)
    ↓
Phase 2 (Comptes + Catégories)  ←  Phase 3 (Transactions) dépend de Phase 2
    ↓                                    ↓
Phase 4 (Budgets)  ←─────────────────────┘
    ↓
Phase 5 (Statistiques + Export)
    ↓
Phase 6 (Sync + Sécurité)
    ↓
Phase 7 (Tests + Déploiement)
```

---

## Suivi

- **Statut** : à mettre à jour au fil de l’avancement (ex. Phase 0 ✅, Phase 1 en cours).
- **Écarts** : noter ici les changements de périmètre ou de délais par rapport à ce plan.
- **Références** : cahier des charges FineTrack, `backend/README.md`.

---

*Document créé pour planifier l’implémentation du backend FineTrack (MVP).*
