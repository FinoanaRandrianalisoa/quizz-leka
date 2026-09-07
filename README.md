# Quizz Web Madagascar — Backend

Plateforme de jeux quizz multijoueurs en temps réel avec dimension sociale, portefeuille
électronique virtuel (mises/gains) et mode spectateur avec paris en direct.

Ce dépôt contient le **backend Django** exposant une API GraphQL, des WebSockets
(Django Channels) pour le temps réel, et des tâches asynchrones (Celery) pour les
paiements et notifications.

## Stack technique

| Composant         | Technologie                                   |
|--------------------|------------------------------------------------|
| Langage / Framework | Python 3.12 / Django 5.x                      |
| API                | GraphQL via [Strawberry](https://strawberry.rocks/) (ASGI natif) |
| Temps réel         | Django Channels (WebSocket + GraphQL Subscriptions) |
| Base de données    | PostgreSQL 16                                  |
| Cache / Broker     | Redis                                          |
| Tâches asynchrones | Celery + Celery Beat                           |
| Authentification   | JWT (access/refresh) + OAuth2 (social login)   |
| Serveur ASGI       | Daphne ou Uvicorn                              |
| Reverse proxy      | Nginx                                          |
| Conteneurisation   | Docker / Docker Compose                        |

Frontend (React) et backend sont déployés sur des **domaines séparés**
(`app.quizz.mg` / `api.quizz.mg`) — CORS configuré en conséquence.

## Structure du projet (backend Django uniquement)

```
quizz-backend/
├── manage.py
├── requirements/
│   ├── base.txt
│   ├── dev.txt
│   └── prod.txt
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── pytest.ini                      # ou setup.cfg pour la config de tests
├── README.md
├── STEPS.md
├── BONNE_PRATIQUE.md
│
├── config/                         # configuration globale du projet Django
│   ├── __init__.py
│   ├── asgi.py                     # point d'entrée ASGI (Channels + Strawberry)
│   ├── wsgi.py                     # conservé si besoin d'un fallback WSGI
│   ├── urls.py                     # routes HTTP (endpoint /graphql/, admin, healthcheck)
│   ├── celery.py                   # instanciation de l'app Celery
│   ├── routing.py                  # routing WebSocket global (Channels)
│   └── settings/
│       ├── __init__.py
│       ├── base.py                 # settings communs
│       ├── dev.py                  # settings développement
│       ├── staging.py              # settings environnement de recette
│       └── prod.py                 # settings production
│
├── schema/                         # assemblage du schéma GraphQL global
│   ├── __init__.py
│   ├── schema.py                   # Query/Mutation/Subscription racine (Strawberry)
│   └── extensions.py               # depth limiting, complexity limiting, rate limiting
│
├── apps/
│   ├── users/                      # RG-USR : profil, parrainage, statistiques
│   │   ├── __init__.py
│   │   ├── models.py                # Utilisateur, PhotoProfil, PhotoCouverture
│   │   ├── managers.py
│   │   ├── types.py                 # types GraphQL (UtilisateurType, ProfilType...)
│   │   ├── queries.py                # resolvers de lecture (profil, statistiques)
│   │   ├── mutations.py              # register, updateProfil, genererCodeParrain
│   │   ├── permissions.py            # règles d'accès spécifiques à l'app
│   │   ├── signals.py                # génération auto du code parrain à la création
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── migrations/
│   │   └── tests/
│   │       ├── test_models.py
│   │       ├── test_mutations.py
│   │       └── test_permissions.py
│   │
│   ├── auth/                        # JWT, refresh tokens, OAuth2, OTP step-up
│   │   ├── models.py                 # RefreshToken, OTPRequest
│   │   ├── jwt.py                    # génération/validation des access/refresh tokens
│   │   ├── otp.py                    # génération, envoi, vérification OTP
│   │   ├── mutations.py               # login, refreshToken, logout, verifyOtp
│   │   ├── middleware.py              # middleware ASGI/Channels d'auth par JWT
│   │   ├── backends.py                # backend OAuth2 / social auth
│   │   ├── permissions.py             # step-up auth requis (décorateur/extension)
│   │   ├── migrations/
│   │   └── tests/
│   │
│   ├── wallet/                      # RG-CPT : portefeuille, ledger, dépôts/retraits
│   │   ├── models.py                 # Portefeuille, LedgerEntry
│   │   ├── services.py                # logique métier (crediter, debiter, transferer)
│   │   ├── selectors.py               # requêtes de lecture optimisées (soldes, historique)
│   │   ├── types.py
│   │   ├── queries.py
│   │   ├── mutations.py               # demanderRetrait, effectuerDepot
│   │   ├── webhooks.py                # endpoints webhooks Mobile Money + vérif HMAC
│   │   ├── tasks.py                   # tâches Celery (traitement paiement, réconciliation)
│   │   ├── permissions.py
│   │   ├── migrations/
│   │   └── tests/
│   │       ├── test_ledger_concurrency.py   # tests de concurrence obligatoires
│   │       └── test_webhooks.py
│   │
│   ├── matches/                     # RG-GAM : moteur de jeu (matchs, tours, questions)
│   │   ├── models.py                  # Match, Tour, Participation, ReponseTour
│   │   ├── consumers.py                # Channels consumer du match (timers, phases)
│   │   ├── services.py                 # logique de score, passage de main, victoire
│   │   ├── tasks.py                    # délai de grâce déconnexion (Celery)
│   │   ├── types.py
│   │   ├── queries.py
│   │   ├── mutations.py                # creerPartie, rejoindrePartie, soumettreReponse
│   │   ├── permissions.py
│   │   ├── migrations/
│   │   └── tests/
│   │
│   ├── betting/                     # RG-SPC / RG-BET : spectateur & paris en direct
│   │   ├── models.py                  # Pari, SignalFraude
│   │   ├── services.py                 # placement, clôture, résolution des paris
│   │   ├── validators.py               # règles anti-fraude (auto-pari, filleul, IP)
│   │   ├── tasks.py                    # résolution asynchrone à la clôture du match
│   │   ├── types.py
│   │   ├── mutations.py                # placerPari
│   │   ├── permissions.py
│   │   ├── migrations/
│   │   └── tests/
│   │       └── test_anti_fraude.py
│   │
│   ├── themes/                      # thèmes et questions (base du moteur de jeu)
│   │   ├── models.py                  # Theme, Question, Reponse
│   │   ├── types.py
│   │   ├── queries.py
│   │   ├── mutations.py                # validerQuestion, ajouterQuestion (admin)
│   │   ├── admin.py
│   │   ├── management/
│   │   │   └── commands/
│   │   │       └── seed_questions.py   # import en masse des questions
│   │   ├── migrations/
│   │   └── tests/
│   │
│   ├── social/                      # RG-SOC : fil d'actualité, amis, défis
│   │   ├── models.py                  # Publication, Commentaire, Reaction, DemandeAmi, Defi
│   │   ├── types.py
│   │   ├── queries.py
│   │   ├── mutations.py
│   │   ├── permissions.py
│   │   ├── migrations/
│   │   └── tests/
│   │
│   ├── discussions/                 # RG-DIS : salons de discussion par ville
│   │   ├── models.py                  # Ville, Message
│   │   ├── consumers.py                # Channels consumer par salon/ville
│   │   ├── types.py
│   │   ├── queries.py
│   │   ├── migrations/
│   │   └── tests/
│   │
│   └── moderation/                  # publicités, modération, supervision admin
│       ├── models.py                  # Publicite, SignalementContenu
│       ├── services.py                 # modération automatique + file de revue
│       ├── types.py
│       ├── mutations.py                # validerPublicite, modererContenu
│       ├── permissions.py              # accès réservé ADMIN (+ sous-permissions)
│       ├── migrations/
│       └── tests/
│
├── common/                          # code partagé entre apps
│   ├── __init__.py
│   ├── models.py                     # modèles/mixins abstraits (TimestampedModel...)
│   ├── graphql/
│   │   ├── errors.py                  # codes d'erreur normalisés (RATE_LIMITED...)
│   │   ├── pagination.py              # pagination standard (cursor/offset)
│   │   └── permissions.py             # décorateurs de permission génériques
│   ├── ratelimit.py                   # implémentation du rate limiting Redis
│   ├── idempotency.py                 # gestion des Idempotency-Key
│   └── utils.py
│
├── infra/                            # fichiers d'infrastructure
│   ├── nginx/
│   │   └── default.conf
│   ├── docker/
│   │   ├── backend.Dockerfile
│   │   └── celery.Dockerfile
│   └── scripts/
│       ├── backup_postgres.sh
│       └── restore_postgres.sh
│
└── staticfiles/                      # collectstatic (admin Django notamment)
```

**Conventions par app** : chaque app métier suit le même découpage
(`models.py` / `types.py` / `queries.py` / `mutations.py` / `permissions.py` /
`tests/`) pour rester prévisible — un développeur qui connaît une app retrouve
immédiatement ses repères dans les autres. Les apps `wallet`, `betting` et
`auth` ont en plus un fichier `services.py` (logique métier isolée des
resolvers) car ce sont les domaines les plus sensibles : la logique doit être
testable indépendamment de la couche GraphQL.

Chaque app expose ses propres types/resolvers/mutations GraphQL, assemblés dans
le schéma unique de `schema/schema.py`. Voir `BONNE_PRATIQUE.md` pour les
règles de sécurité par domaine (notamment `wallet` et `betting`, sensibles).

## Démarrage rapide (développement)

### Docker Compose (recommandé)

Le dépôt racine contient un `docker-compose.yml` qui orchestre
**postgres + redis + backend (Daphne/ASGI) + Celery (worker/beat) + Flower +
frontend (nginx)**. Les migrations et les seeds sont exécutés automatiquement
par le service `migrate` au premier démarrage.

```bash
# À la racine du dépôt (comme `docker-compose.yml`)
cp Back/.env.example Back/.env

# Démarrer toute la stack
docker compose up -d --build

# Accéder aux services
# API GraphQL (GraphiQL) : https://quizz-leka-production.up.railway.app/graphql/
# Frontend (nginx)       : http://localhost:8443/
# Flower (Celery UI)     : http://localhost:5555/
```

Le service `migrate` exécute `migrate`, `seed_questions` puis `seed_demo` :
les comptes de démonstration sont
`rakoto@example.mg / rabe@example.mg / rasoa@example.mg` (mot de passe
`MotDePasse1!`, saldo de départ crédité).

### Sans Docker (local)

```bash
# 1. Python 3.10+ + PostgreSQL/Redis (- Docker non requis pour vérifier via SQLite)
pip install -r requirements/dev.txt

# 2. Copier la config et l'adapter (DATABASE_URL, REDIS_URL...)
cp .env.example .env

# 3. Migrations + seeds
python manage.py migrate --noinput
python manage.py seed_questions
python manage.py seed_demo
python manage.py createsuperuser

# 4. Lancer le serveur ASGI (HTTP + WebSockets)
daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

Pour une vérification rapide **sans PostgreSQL/Redis** (SQLite en mémoire pour
les tests, fichier pour le run manuel) :

```powershell
$env:DATABASE_URL="sqlite:///./db_verify.sqlite3"
python manage.py migrate --noinput
python manage.py seed_demo
daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

### Tests

```bash
python -m pytest
```

## Variables d'environnement clés

Voir `.env.example` pour la liste complète. Les plus critiques :

- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`
- `DATABASE_URL` (PostgreSQL)
- `REDIS_URL` (broker Celery + channel layer Channels)
- `JWT_ACCESS_TTL`, `JWT_REFRESH_TTL`
- `CORS_ALLOWED_ORIGINS`
- `MOBILE_MONEY_*` (clés API MVola / Orange Money / Airtel Money + secret webhook)
- `OTP_PROVIDER_*` (Twilio / Africa's Talking)

**Aucun secret ne doit être commité.** Utiliser `.env` local et un vault en production.

## Documentation associée

- [`STEPS.md`](./STEPS.md) — feuille de route de développement, par étapes.
- [`BONNE_PRATIQUE.md`](./BONNE_PRATIQUE.md) — règles de sécurité et bonnes pratiques
  à respecter impérativement (authentification, GraphQL, transactions financières,
  infrastructure).

## Documents de référence projet

- Cahier des charges & règles de gestion (RG-USR, RG-SOC, RG-CPT, RG-GAM, RG-SPC, RG-BET)
- Diagramme de cas d'utilisation
- Modèle Conceptuel de Données (MCD)
- Diagramme de séquence (déroulement d'un match)