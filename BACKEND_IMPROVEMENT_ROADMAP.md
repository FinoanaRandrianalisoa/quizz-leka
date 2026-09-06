# BACKEND_IMPROVEMENT_ROADMAP

Ce document est le plan de référence pour améliorer progressivement le backend QuizMada.

Il a été construit à partir d’une analyse du code réel du repository et ne prétend pas corriger l’architecture en une seule fois. L’objectif est de faire des améliorations petites, vérifiables, testées et déployables par étapes.

> Phase actuelle : audit + plan d’action.
> Aucune modification applicative du code n’a été faite pendant cette phase.

---

## 1. OBJECTIF DE L’AUDIT

Le backend actuel est une plateforme Django orientée jeu social et temps réel. Sur le code observé, il combine :
- Django ORM
- GraphQL via Strawberry
- Django Channels / WebSockets
- JWT maison
- Redis comme Channel Layer et cache
- Celery pour tâches asynchrones
- PostgreSQL comme base de données principale

L’objectif de l’amélioration est de transformer ce backend en une base plus sûre, plus lisible, plus robuste et plus évolutive, sans réécrire l’ensemble du système d’un coup.

---

## 2. ANALYSE RÉELLE DU REPOSITORY

### 2.1. Architecture confirmée dans le code

#### GraphQL
- Le schéma global est assemblé dans `schema/schema.py`.
- Le endpoint principal est exposé via `config/urls.py` sur `/graphql/`.
- Les permissions sont centralisées dans `common/graphql/permissions.py`.
- Les erreurs métier sont normalisées dans `common/graphql/errors.py` et `common/graphql/errors_handler.py`.
- Le middleware GraphQL a une logique de validation/normalisation dans `schema/extensions.py`.

#### Authentification
- Le JWT est géré dans `apps/auth/jwt.py`.
- Le middleware JWT HTTP et WebSocket est dans `apps/auth/middleware.py`.
- La configuration des TTL et secret est dans `config/settings/base.py`.

#### WebSockets
- Les routes WebSocket sont déclarées dans `config/routing.py`.
- Les consumers principaux sont dans :
  - `apps/discussions/consumers.py`
  - `apps/matches/consumers.py`
- L’ASGI app est configurée dans `config/asgi.py`.

#### Redis / Channels / Cache
- Le Channel Layer est configuré dans `config/settings/base.py`.
- Les CACHES utilisent Redis.
- La configuration Celery est également basée sur Redis.

#### Jeux / matchs / RPS
- La logique de match et de tour est dans `apps/matches/services.py`.
- Les structures mémoire suivantes sont clairement visibles :
  - `RPS_CHALLENGES: dict[str, dict] = {}`
  - `RPS_MATCHES: dict[str, dict] = {}`
- Les GraphQL mutations pour les défis RPS sont exposées dans `apps/matches/mutations.py`.
- Les queries pour récupérer les défis sont dans `apps/matches/queries.py`.

#### Wallet / transactions / paris
- `apps/wallet/` est présent et configuré.
- La conception de la logique de ledger/transactions est importante dans un système de jeu avec gains/mises.

#### Social / notifications
- `apps/social/services.py` envoie des notifications WebSocket.
- Le type de notification est géré dans `apps/social/models.py`.
- Les classes de notifications / social / discussions sont clairement séparées.

---

## 3. CONFIRMÉ DANS LE CODE : POINTS FORTS

### 3.1. Bonnes bases observées

- Séparation fonctionnelle par domaine (`apps/*`).
- Authentification centralisée dans `apps/auth`.
- GraphQL centralisé dans `schema/`.
- WebSockets structurés via `config/routing.py`.
- Utilisation de Redis pour le Channel Layer et les caches.
- Support de `Django Channels` realistic.
- Config de sécurité partielle déjà présente : `CORS` + `PASSWORD_HASHERS` + `DEBUG` et `ALLOWED_HOSTS` dans settings.
- Les exceptions de domaine sont déjà organisées dans `common/graphql/errors.py`.

### 3.2. Points qui montrent une architecture saine mais fragile

- Les services préparent la logique métier avec des fonctions séparées.
- Les modules sont structurés par responsabilité fonctionnelle.
- L’architecture actuelle est proche d’une architecture en couches avec service layer.
- Les WebSockets sont bien intégrés au projet.

Cependant, plusieurs zones restent sensibles et doivent être améliorées.

---

## 4. PROBLÈMES DÉCOUVERTS ET CLASSIFICATION

### 🔴 Problème critique 1 — RPS en mémoire globale, non multi-instance

#### Confirmé dans le code
Dans `apps/matches/services.py` :

```python
RPS_CHALLENGES: dict[str, dict] = {}
RPS_MATCHES: dict[str, dict] = {}
```

Cela signifie que les défis et parties RPS sont stockés en mémoire interne du processus Python.

#### Risque
- non compatible avec plusieurs instances du backend ;
- les utilisateurs connectés à une autre instance ne voient pas l’état partagé ;
- perte de données lors d’un reload du worker ou d’un redémarrage ;
- incohérence si plusieurs workers Django / ASGI sont lancés.

#### Classification
- 🔴 Problème critique

#### Recommandation
Migrer les défis RPS et les statuts de partie vers Redis ou une base persistée, avec une clé unique stable et un mécanisme d’expiration.

---

### 🔴 Problème critique 2 — contraintes de transaction / wallet / gains / paris

#### Confirmé dans le code
Le projet contient des modules `wallet`, `betting`, `matches` et `social` qui interagissent entre eux. L’architecture montre des domaines fortement dépendants.

#### Risque
Les opérations de mise, gain, remboursement, score, fin de match et notification peuvent être affectées par :
- race conditions ;
- double crédit / double débit ;
- traitements incohérents en cas de retry ;
- transactions incomplètes ;
- notifications envoyées sans état finalement cohérent.

#### Classification
- 🔴 Problème critique

#### Recommandation
Appliquer une stratégie stricte d’atomicité avec :
- `transaction.atomic()` ;
- `select_for_update()` pour les ressources critiques ;
- idempotence sur les actions de wallet et betting ;
- ledger unique, journal des opérations ;
- transaction ID pour chaque action de paiement / gain / remboursement.

---

### 🟠 Problème important 1 — responsabilités de service et service layer encore dispersées

#### Confirmé dans le code
Les modules `mutations.py`, `queries.py`, `services.py`, `types.py` et `consumers.py` coexistent dans chaque domaine, mais la logique métier se mélange encore parfois à la logique technique.

#### Risque
- duplication de logique ;
- comportement dépendant du contexte GraphQL/WS ;
- tests plus difficiles à écrire ;
- maintenance plus coûteuse lors d’ajout de règles métier.

#### Classification
- 🟠 Important

#### Recommandation
Préserver le Service Layer existant mais renforcer la séparation :
- mutation = orchestration ;
- service = logique métier ;
- repository / data access = accès DB ;
- consumer = émission d’événements uniquement.

---

### 🟠 Problème important 2 — WebSockets peuvent recevoir des payloads lourds et peu standardisés

#### Confirmé dans le code
Les consumers utilisent `group_send` avec des structures de données relatively dynamiques. La logique de broadcast est présente dans les services et les consumers.

#### Risque
- payloads volumineux ;
- variantes de messages difficiles à valider ;
- couplage fort entre frontend et backend ;
- moins de robustesse en cas de réécriture ou de reconnexion.

#### Classification
- 🟠 Important

#### Recommandation
Standardiser les événements WebSocket avec un schéma fixé :
- `type`
- `event_id`
- `timestamp`
- `version`
- `data`

---

### 🟡 Amélioration recommandée 1 — sécurité et production hardening

#### Confirmé dans le code
Les settings contiennent `DEBUG`, `ALLOWED_HOSTS`, `CORS`, `JWT_SECRET`, `REDIS_URL`, etc., ce qui est bon. Cependant, certaines protections importantes doivent être renforcées.

#### Risque
- `DEBUG` peut être activé en production si non contrôlé ;
- `ALLOWED_HOSTS` et CORS nécessitent un examen strict d’environnement ;
- sécurité Redis / PostgreSQL / Celery peut rester insuffisante sans hardening ;
- WebSocket auth doit être renforcée si les tokens ne sont pas vérifiés assez strictement.

#### Classification
- 🟡 Recommandée

#### Recommandation
- production settings séparées ;
- introspection GraphQL désactivée ;
- logs sans données sensibles ;
- sécurité HTTP/WSS détaillée ;
- limites de requêtes ;
- rate limiting sélectif.

---

### 🟡 Amélioration recommandée 2 — observabilité et logging

#### Confirmé dans le code
Le logging est présent mais reste assez basique dans `config/settings/base.py`.

#### Risque
- difficulté à diagnostiquer les erreurs temps réel ;
- manque de correlation id ;
- manque de métriques de performance ;
- impossible de distinguer les causes de lenteur / queue / Redis / DB.

#### Classification
- 🟡 Recommandée

#### Recommandation
Mettre en place :
- request ID et correlation ID ;
- logs structurés ;
- métriques sur WS, GraphQL, DB, Redis ;
- p50/p95/p99 ;
- alertes sur erreurs de channel layer / DB / wallet.

---

### 🟢 Optimisation optionnelle 1 — CQRS / DataLoader / query optimization

#### Confirmé dans le code
Les GraphQL queries peuvent très vite devenir lourdes dans un système avec profils, amis, notifications, parties, messages, wallet, etc.

#### Risque
- N+1 queries ;
- requêtes lourdes en lecture ;
- latence montée lorsqu’un utilisateur ouvre plusieurs sections simultanément.

#### Classification
- 🟢 Optimisation optionnelle

#### Recommandation
- utiliser `select_related` / `prefetch_related` au besoin ;
- ajouter des loaders si la complexité augmente ;
- éviter les sous-requêtes inutiles dans les types GraphQL ;
- valider la profondeur de requêtes GraphQL.

---

## 5. ARCHITECTURE ACTUELLE VERSUS ARCHITECTURE CIBLE

### 5.1. Architecture actuelle observée

```text
Client
  │
  ├── GraphQL
  │
  └── WebSocket
       │
       ▼
  Django + Strawberry + Channels
       │
       ├── Mutations / Queries
       │
       ├── Services
       │
       ├── Models
       │
       ├── Consumers
       │
       └── Redis / PostgreSQL / Celery
```

### 5.2. Architecture cible recommandée

```text
Client
  │
  ├── GraphQL
  │
  └── WebSocket
       │
       ▼
   Interface layer
       │
       ▼
   Application services
       │
       ├── auth
       ├── users
       ├── matches
       ├── rps
       ├── social
       ├── wallet
       ├── betting
       └── moderation
       │
       ▼
   Domain layer
       │
       ├── entities
       ├── value objects
       ├── domain rules
       ├── state machines
       └── policies
       │
       ▼
   Infrastructure layer
       │
       ├── PostgreSQL / ORM
       ├── Redis cache
       ├── Redis channel layer
       ├── Celery tasks
       └── external integrations
```

### 5.3. Pourquoi cette cible est pertinente ici

Parce que le projet est un backend social + jeu + temps réel + wallet + paris. Il ne doit pas rester purement “Django views + GraphQL resolvers” sans frontières nettes.

L’architecture cible reste pragmatique :
- simple à comprendre ;
- compatible avec Django ;
- évolutive ;
- testable ;
- sécurisée ;
- proche du code existant sans gros refactor big bang.

---

## 6. DESIGN PATTERNS À UTILISER (JUSTIFIÉS)

### Service Layer
Oui, c’est le bon point de départ. Le code actuel a déjà cette logique. Il faut simplement la rendre plus nette.

### Repository Pattern
À utiliser uniquement si l’accès aux données devient trop dispersé ou si des règles SQL répétitives se multiplient. Pas nécessaire dès maintenant dans tout le projet, mais utile pour les sections critiques comme wallet / betting / matches.

### Unit of Work
Très utile pour les transactions de wallet, gains et paris. Les actions doivent être atomiques et auditable.

### Strategy Pattern
À envisager pour :
- calcul de score ;
- choix de rules du match ;
- règles de gain ;
- calcul de récompense.

### State Pattern
Très utile pour les états de match et de défi RPS.

Exemples :
- `WAITING`, `STARTED`, `FINISHED`, `CANCELLED`
- `PENDING`, `ACCEPTED`, `PLAYING`, `FINISHED`, `EXPIRED`

### Event Pattern / Observer
Très adapté à la logique de notifications, tour terminé, score mis à jour, reward distribué.

### Adapter Pattern
À utiliser pour services externes (Redis, email, mobile money, fournisseur OTP, etc.).

### Facade Pattern
À utiliser pour simplifier l’accès à plusieurs services dans des mutations complexes.

### CQRS
À éviter en premier lieu. Le backend actuel n’a pas encore de besoin clair suffisamment important pour justifier CQRS complet.

---

## 7. REDIS ET MULTI-INSTANCE

### 7.1. Ce que le code confirme
Le backend configure Redis à la fois pour :
- Channel Layer
- cache
- Celery broker

### 7.2. Ce que cela implique
Redis est déjà un composant central. On peut donc l’utiliser pour des structures temporaires critiques qui ne doivent pas rester en mémoire Python locale.

### 7.3. Recommandation
Pour la logique RPS et les états temporaires :
- remplacer les `dict` en mémoire par des clés Redis ;
- utiliser TTL sur les challenges ;
- stocker des états dans un format standardisé ;
- faire l’ID de défi / match explicite et persistant.

Exemple de logique recommandée :

```text
Redis keys:
- rps:challenge:<id>
- rps:match:<id>
- rps:challenge:pending:<user_id>
```

Cela permet d’avoir un backend multi-instance sans perte de cohérence.

---

## 8. SÉCURITÉ : CHECKLIST

### Security Checklist
- [ ] JWT access token court et vérifié strictement
- [ ] Refresh token séparé et géré de manière sécurisée
- [ ] Authentification WebSocket vérifiée
- [ ] Authorization GraphQL et WebSocket contrôlée
- [ ] Permissions objet / utilisateur vérifiées
- [ ] Validation des entrées centralisée
- [ ] Rate limiting sur mutations sensibles
- [ ] Protection contre brute force / spam / abuse
- [ ] Secrets externes stockés dans l’environnement
- [ ] Production settings distinctes de dev settings
- [ ] CORS strictement limité
- [ ] Introspection GraphQL désactivée en prod
- [ ] Logs sans données sensibles
- [ ] Redis / PostgreSQL sécurisés
- [ ] Variables sensibles non envoyées dans les réponses

---

## 9. WALLET / BETTING / TRANSACTIONS : RÈGLE DE SÉCURITÉ

Le système de wallet, gains et paris doit être traité comme critique.

### Recommandations obligatoire
- `transaction.atomic()` autour des opérations de mutation de solde
- `select_for_update()` sur les comptes clés
- une table de ledger ou journaling dédiée
- un `transaction_id` unique pour chaque mouvement
- idempotence sur les actions critiques
- double-check sur le total du solde après chaque mise/gain/récompense
- validation avant et après l’écriture

### Risques à surveiller
- double débit
- double remboursement
- double récompense
- rejet partiel d’une requête lors de crash intermédiaire
- états incohérents entre wallet, notification et match

---

## 10. GESTION DES ERREURS

Le projet a déjà une structure de base pour les exceptions GraphQL. Il faut la renforcer en créant un vrai système de exceptions métier.

### Recommandation
Créer un registre clair de exceptions métier :
- `DomainError`
- `ValidationError`
- `PermissionDeniedError`
- `NotFoundError`
- `ConflictError`
- `RateLimitedError`
- `IdempotencyError`
- `WalletError`
- `MatchStateError`

Le but est d’avoir :
- des erreurs standardisées ;
- des codes explicites ;
- des messages fiables ;
- un comportement cohérent GraphQL / WebSocket.

---

## 11. OBSERVABILITÉ

Le backend doit être instrumenté pour mesurer l’état réel du système.

### À mettre en place
- logs structurés
- correlation ID
- request ID
- event ID pour WebSocket
- métriques de performances
- alertes sur Redis / DB / Channels / Celery
- dashboards sur :
  - connexions WS
  - notifications en temps réel
  - erreurs de mutation
  - latence GraphQL
  - paramètres de wallet / betting

---

## 12. TESTS À PRIORISER

### Tests de base
- tests GraphQL des mutations et queries critiques
- tests du cycle de match
- tests du cycle RPS
- tests notification -> acceptation
- tests wallet / transaction / gains
- tests permission/auth
- tests WebSocket des événements de partie

### Tests de concurrence
- double mise sur le même match
- double acceptation du même défi
- verification des états de match après simultanéité
- gestion d’état RPS concurrent

### Critère de qualité
Aucune amélioration critique ne doit être validée sans tests ciblés.

---

## 13. PLAN D’AMÉLIORATION PAR PHASES

### PHASE 0 — Audit et sécurisation du socle

#### [SEC-001] Sécuriser la configuration et le hardening de production
- Priorité : 🔴 Critique
- Catégorie : Sécurité
- Difficulté : Moyenne
- Dépendances : -
- Objectif : sécuriser les paramètres environnementaux et la production
- Problème actuel : le backend a des paramètres de base mais un hardening prod plus léger que nécessaire
- Pourquoi c’est important : évite les dérives et les mauvaises configurations
- Fichiers concernés : `config/settings/*`, `.env`, `.env.example`
- Architecture actuelle : settings centralisés mais non divisés strictement par environnement de sécurité
- Architecture cible : settings distincts et robustes pour dev/staging/prod
- Design Pattern : Adapter / config layer
- Modifications à effectuer :
  - séparer les settings ;
  - verrouiller `DEBUG` ;
  - sécuriser `ALLOWED_HOSTS` ;
  - vérifier les secrets ;
  - renforcer CORS ;
  - désactiver l’introspection GraphQL en production.
- Sécurité : élevé
- Performance : faible
- Tests à créer : tests de chargement des settings / validation des variables
- Critères de validation : config prod validée et sécurisée
- Risques : impact faible si bien fait
- Rollback possible : oui, via config revert
- Statut : ⬜ À faire

#### [SEC-002] Renforcer l’authentification JWT et WebSocket
- Priorité : 🔴 Critique
- Catégorie : Sécurité
- Difficulté : Moyenne
- Dépendances : SEC-001
- Objectif : sécuriser les flux d’authentification
- Problème actuel : le JWT et la vérification WS existent mais leur politique de validation doit être renforcée
- Pourquoi c’est important : les connexions WebSocket et les appels GraphQL doivent être authentifiés rigidement
- Fichiers concernés : `apps/auth/middleware.py`, `apps/auth/jwt.py`, `common/graphql/permissions.py`
- Architecture actuelle : JWT maison + middleware central
- Architecture cible : garde le JWT, mais validation plus explicite, stricte et uniforme
- Design Pattern : Adapter / façade
- Modifications à effectuer :
  - validation stricte des claims ;
  - forbiddance des valeurs anonymes ;
  - logging minimal ;
  - sécurité sur query token pour WebSocket.
- Sécurité : très élevé
- Performance : faible
- Tests à créer : tests JWT invalide / JWT expiré / mauvais type / WS sans token
- Critères de validation : chaque flux est refusé proprement en cas de mauvais JWT
- Risques : petite régression si tokens dupliqués ou invalides
- Rollback possible : oui
- Statut : ⬜ À faire

---

### PHASE 1 — Architecture et séparation des responsabilités

#### [ARCH-001] Clarifier le Service Layer par domaine
- Priorité : 🟠 Haute
- Catégorie : Architecture
- Difficulté : Moyenne
- Dépendances : SEC-001
- Objectif : séparer logique métier et orchestration
- Problème actuel : mutatons / services / consumers sont encore fortement couplés
- Pourquoi c’est important : rend le code maintenable et testable
- Fichiers concernés : `apps/*/mutations.py`, `apps/*/services.py`, `apps/*/queries.py`
- Architecture actuelle : couches mélangées
- Architecture cible : mutation = orchestration, service = métier, consumer = events
- Design Pattern : Service Layer + Facade
- Modifications à effectuer :
  - extraire les règles métier dans des services dédiés ;
  - réduire la logique dans les resolvers ;
  - créer des services réutilisables entre GraphQL et WS.
- Sécurité : moyenne
- Performance : positive à moyen terme
- Tests à créer : tests de services et intégration GraphQL
- Critères de validation : logique métier isolée et testable
- Risques : refactoring de fonctions partagées
- Rollback possible : oui, avec commits unitaires
- Statut : ⬜ À faire

#### [ARCH-002] Standardiser les événements WebSocket
- Priorité : 🟠 Haute
- Catégorie : Temps réel
- Difficulté : Moyenne
- Dépendances : ARCH-001
- Objectif : rendre les événements WS plus stables et plus légers
- Problème actuel : messages plus “ad hoc” que nommés / standardisés
- Pourquoi c’est important : évite les régressions frontend/backend et les incompatibilités
- Fichiers concernés : `config/routing.py`, `apps/*/consumers.py`, services de broadcast
- Architecture actuelle : broadcast direct sans contrat fort
- Architecture cible : contrat de message standardisé avec versioning
- Design Pattern : Event / Observer
- Modifications à effectuer :
  - normaliser `type`, `event_id`, `timestamp`, `version`, `data` ;
  - documenter les payloads ;
  - gérer reconnexion / ordering.
- Sécurité : moyenne
- Performance : élevée
- Tests à créer : tests WS event schema
- Critères de validation : tous les événements suivent un format standard
- Risques : frontend doit être aligné
- Rollback possible : oui
- Statut : ⬜ À faire

---

### PHASE 2 — Data consistency / wallet / matches / gaming logic

#### [DB-001] Sécuriser les transactions wallet et betting
- Priorité : 🔴 Critique
- Catégorie : Wallet / Transactions
- Difficulté : Difficile
- Dépendances : ARCH-001
- Objectif : éliminer les risques de double débit / crédit / récompense
- Problème actuel : les systèmes de gains et de mises interagissent entre plusieurs modules sans cadre de transaction explicite assez fort
- Pourquoi c’est important : c’est un risque métier et financier direct
- Fichiers concernés : `apps/wallet/*`, `apps/betting/*`, `apps/matches/services.py`
- Architecture actuelle : logique métier répartie sur plusieurs modules
- Architecture cible : ledger + atomic update + idempotence
- Design Pattern : Unit of Work + Strategy
- Modifications à effectuer :
  - verrouillage des comptes ;
  - ledger unique ;
  - idempotence ;
  - transactions atomiques ;
  - règles de récompense explicites.
- Sécurité : très élevé
- Performance : moyenne
- Tests à créer : tests de double appel, double gain, double perte
- Critères de validation : pas de double crédit / débit
- Risques : complexité de migration et test de régression
- Rollback possible : oui mais avec migration cible
- Statut : ⬜ À faire

#### [MATCH-001] Refactor du cycle de match et de tour
- Priorité : 🟠 Haute
- Catégorie : Match / gameplay
- Difficulté : Difficile
- Dépendances : ARCH-001
- Objectif : rendre le moteur de match plus explicite et plus testable
- Problème actuel : logique de tour, score, résolution, ouverture du tour et clôture partagés dans le service
- Pourquoi c’est important : cela réduit les bugs métier et les cas limites
- Fichiers concernés : `apps/matches/services.py`, `apps/matches/models.py`
- Architecture actuelle : service très dense
- Architecture cible : state machine de match + service de tour + service de résolution
- Design Pattern : State Pattern + Strategy
- Modifications à effectuer :
  - séparer état de match ;
  - séparer calcul du score ;
  - séparer clôture de match ;
  - verrouiller l’état.
- Sécurité : moyenne
- Performance : positive
- Tests à créer : tests de clôture, tour expiré, score cible, match annulé
- Critères de validation : match toujours dans un état cohérent
- Risques : régression sur logique métier existante
- Rollback possible : oui, par étape
- Statut : ⬜ À faire

---

### PHASE 3 — Redis / WebSockets / RPS multi-instance

#### [RPS-001] Migrer les challenges RPS hors mémoire locale
- Priorité : 🔴 Critique
- Catégorie : Temps réel / architecture
- Difficulté : Difficile
- Dépendances : ARCH-002
- Objectif : rendre le système RPS compatible avec plusieurs instances backend
- Problème actuel : `RPS_CHALLENGES` et `RPS_MATCHES` sont des `dict` en mémoire Python dans `apps/matches/services.py`
- Pourquoi c’est important : c’est une vraie limitation de scalabilité et de fiabilité
- Fichiers concernés : `apps/matches/services.py`, `apps/matches/mutations.py`, `apps/matches/queries.py`
- Architecture actuelle : global Python dict, non partagé entre workers
- Architecture cible : Redis-backed state + TTL + event-driven updates
- Design Pattern : Repository / Adapter + State Pattern
- Modifications à effectuer :
  - remplacer dict global par structures Redis persistées ;
  - ajouter TTL / expiration ;
  - migrer les événements de challenge ;
  - gérer acceptation unique et expiration.
- Sécurité : moyenne
- Performance : très bonne après migration
- Tests à créer : conflit de défi, acceptation unique, expiration, multi-instance simulation
- Critères de validation : 2 instances backend voient le même état RPS
- Risques : migration délicate si dépendance forte au code existant
- Rollback possible : oui via versioning de la clé Redis
- Statut : ⬜ À faire

#### [WS-001] Standardiser les groupes et événements temps réel
- Priorité : 🟠 Haute
- Catégorie : WebSockets
- Difficulté : Moyenne
- Dépendances : RPS-001, ARCH-002
- Objectif : améliorer la stabilité de la communication live
- Problème actuel : groupes et payloads peuvent varier selon les domaines
- Pourquoi c’est important : prévenir les incohérences ou messages incomplets
- Fichiers concernés : `config/routing.py`, `apps/discussions/consumers.py`, `apps/matches/consumers.py`
- Architecture actuelle : groupes direct et messages ad hoc
- Architecture cible : conventions de message, groupes nommés de manière explicite et stable
- Design Pattern : Event / Observer
- Modifications à effectuer :
  - documenter les groupes ;
  - gérer reconnexion ;
  - heartbeat ;
  - ordering ;
  - backpressure / rate limit.
- Sécurité : moyenne
- Performance : élevée
- Tests à créer : tests de groupe, reconnect, payload, timeout
- Critères de validation : les événements arrivent correctement et dans l’ordre logique
- Risques : comportement frontend à aligner
- Rollback possible : oui
- Statut : ⬜ À faire

---

### PHASE 4 — Performance, données, ORM et GraphQL

#### [DB-002] Optimiser les queries ORM et les N+1
- Priorité : 🟠 Haute
- Catégorie : PostgreSQL / ORM
- Difficulté : Moyenne
- Dépendances : ARCH-001
- Objectif : réduire la charge DB
- Problème actuel : le backend contient plusieurs domaines liés (matchs, notifications, profils, messages, amis, wallet) et les requêtes peuvent devenir lourdes
- Pourquoi c’est important : la plateforme doit rester fluide avec plusieurs utilisateurs
- Fichiers concernés : modules queries, models, serializers si présents
- Architecture actuelle : ORM standard sans optimisation lourde détaillée
- Architecture cible : `select_related`, `prefetch_related`, filtres ciblés, indexation réelle
- Design Pattern : query optimization layer
- Modifications à effectuer :
  - indexer colonnes fréquentes ;
  - précharger relations ;
  - éviter les requêtes nested inutiles ;
  - sortir les agrégats lourds.
- Sécurité : faible
- Performance : élevée
- Tests à créer : tests benchmark + vérification des requêtes
- Critères de validation : réduction nette des N+1 et des temps de réponse
- Risques : risque d’augmentation du coût de maintenance si suroptimisé sans mesure
- Rollback possible : oui
- Statut : ⬜ À faire

#### [GQL-001] Renforcer GraphQL security et query quality
- Priorité : 🟠 Haute
- Catégorie : GraphQL
- Difficulté : Moyenne
- Dépendances : SEC-001, ARCH-001
- Objectif : sécuriser l’API GraphQL et réduire les coûts de requêtes
- Problème actuel : GraphQL est central et puissant, donc il faut sécuriser ses accès et ses profondeurs
- Pourquoi c’est important : GraphQL peut devenir un point de saturation ou de vulnérabilité si pas maîtrisé
- Fichiers concernés : `schema/schema.py`, `schema/extensions.py`, `common/graphql/*`
- Architecture actuelle : GraphQL centralisé avec gestion des erreurs et permissions déjà partiellement mise en place
- Architecture cible : GraphQL plus strict, plus mesuré, plus documenté
- Design Pattern : Adapter + validation layer
- Modifications à effectuer :
  - validations ;
  - rate limiting ;
  - pagination ;
  - query complexity ;
  - logs de requêtes lourdes.
- Sécurité : très élevé
- Performance : élevée
- Tests à créer : tests de permissions, over-fetch, payloads trop lourds
- Critères de validation : requêtes interdites ou limitées correctement
- Risques : régressions sur clients GraphQL existants
- Rollback possible : oui
- Statut : ⬜ À faire

---

### PHASE 5 — Observabilité et préparation au scaling

#### [OBS-001] Mettre en place observabilité produite
- Priorité : 🟡 Moyenne
- Catégorie : Monitoring
- Difficulté : Moyenne
- Dépendances : SEC-001, ARCH-002
- Objectif : rendre le backend diagnosable en production
- Problème actuel : logs de base présents mais insuffisants pour le système temps réel
- Pourquoi c’est important : les bugs temps réel sont souvent très difficiles à diagnostiquer sans tracing
- Fichiers concernés : `config/settings/base.py`, `apps/*/services.py`, `common/*`
- Architecture actuelle : logging basique
- Architecture cible : logs structurés + métriques + traces
- Design Pattern : instrumentation layer
- Modifications à effectuer :
  - correlation ID ;
  - logs sur mutations critiques ;
  - monitor des WS ;
  - alertes sur Redis/PostgreSQL/Celery.
- Sécurité : moyenne
- Performance : positive
- Tests à créer : tests de log structure / correlation ID
- Critères de validation : erreurs suivables en production
- Risques : volume de logs élevé si mal réglé
- Rollback possible : oui
- Statut : ⬜ À faire

#### [SCALE-001] Préparer le scaling horizontal
- Priorité : 🟢 Basse
- Catégorie : Scalabilité
- Difficulté : Difficile
- Dépendances : RPS-001, WS-001, OBS-001
- Objectif : rendre le backend compatible avec plusieurs instances
- Problème actuel : le RPS et les états temporaires sont encore dépendants de l’état du processus
- Pourquoi c’est important : cela limite l’évolution du projet si la charge augmente
- Fichiers concernés : graphes de services, config Redis, consumers, store d’état
- Architecture actuelle : monolithique avec Redis déjà présent mais usage incomplet pour l’état métier
- Architecture cible : état partagé via Redis + instances stateless
- Design Pattern : distributed state + event bus
- Modifications à effectuer :
  - externaliser les états ;
  - organiser les consumers pour plusieurs workers ;
  - surveiller les événements en queue.
- Sécurité : moyenne
- Performance : très haute
- Tests à créer : tests multi-instance / failover / session continuity
- Critères de validation : le système reste cohérent sur plusieurs workers
- Risques : architecture plus complexe
- Rollback possible : oui avec versioning et rollback de configuration
- Statut : ⬜ À faire

---

## 14. SYSTÈME DE SUIVI DES TÂCHES

| ID | Amélioration | Priorité | Difficulté | Dépendances | Statut |
|---|---|---|---|---|---|
| SEC-001 | Sécuriser la config et le hardening production | 🔴 | Moyenne | - | ⬜ |
| SEC-002 | Renforcer JWT et WebSocket auth | 🔴 | Moyenne | SEC-001 | ⬜ |
| ARCH-001 | Clarifier le Service Layer | 🟠 | Moyenne | SEC-001 | ⬜ |
| ARCH-002 | Standardiser les événements WebSocket | 🟠 | Moyenne | ARCH-001 | ⬜ |
| DB-001 | Sécuriser wallet / betting / transactions | 🔴 | Difficile | ARCH-001 | ⬜ |
| MATCH-001 | Refactor du cycle de match et de tour | 🟠 | Difficile | ARCH-001 | ⬜ |
| RPS-001 | Migrer les challenges RPS hors mémoire locale | 🔴 | Difficile | ARCH-002 | ⬜ |
| WS-001 | Standardiser les groupes et messages temps réel | 🟠 | Moyenne | ARCH-002 | ⬜ |
| DB-002 | Optimiser queries ORM et N+1 | 🟠 | Moyenne | ARCH-001 | ⬜ |
| GQL-001 | Renforcer GraphQL security et query quality | 🟠 | Moyenne | SEC-001 | ⬜ |
| OBS-001 | Mettre en place observabilité | 🟡 | Moyenne | SEC-001 | ⬜ |
| SCALE-001 | Préparer le scaling horizontal | 🟢 | Difficile | RPS-001, WS-001 | ⬜ |

---

## 15. ORDRE D’EXÉCUTION ET DÉPENDANCES

### 1. Ce qu’il faut faire en premier
1. sécuriser les settings et JWT ;
2. sécuriser les transactions wallet / betting ;
3. refactorer les services critiques ;
4. migrer les états RPS hors mémoire locale ;
5. standardiser les événements temps réel ;
6. optimiser DB et GraphQL ;
7. ajouter l’observabilité ;
8. préparer le scaling.

### 2. Ce qui dépend de quoi
```text
SEC-001 -> SEC-002 -> ARCH-001 -> DB-001 / MATCH-001 / DB-002 / GQL-001
ARCH-001 -> ARCH-002 -> WS-001 -> RPS-001 -> SCALE-001
ARCH-002 -> OBS-001
SEC-001 -> OBS-001
```

---

## 16. QUICK WINS

Les quick wins sont les améliorations rapides que l’on peut mettre en place sans gros refactor.

### Exemple de quick wins confirmés dans le code
- sécuriser les configs de production ;
- renforcer les permissions GraphQL ;
- normaliser les codes d’erreurs GraphQL ;
- centraliser les logs ;
- indexer les champs de recherche et de jointure fréquents ;
- utiliser `select_related` / `prefetch_related` sur les queries critiques ;
- limiter les payloads WebSocket ;
- standardiser les événements de notification.

### À faire en priorité
- validation centralisée des entrées ;
- logs structurés ;
- protection GraphQL ;
- audit des comptes wallet ;
- TTL sur événements temporaires ;
- ajout de tests de validation sur les mutations critiques.

---

## 17. MAJOR REFACTORINGS

### Refonte majeure recommandée
- extraire le domain logic des services en couches plus nettes ;
- introduire un layer d’état pour les matchs et les défis ;
- externaliser les états temporaires depuis le processus Python vers Redis ;
- mettre en place des transactions wallet robustes ;
- rendre les consumers plus standards et plus testables ;
- améliorer la traçabilité via ID de correlation.

---

## 18. ROADMAP PAR PRIORITÉ

### 🔴 PRIORITÉ CRITIQUE
- SEC-001 : sécurisation config / production
- SEC-002 : JWT & WebSocket auth
- DB-001 : wallet / transactions / betting
- RPS-001 : migration du stockage RPS hors mémoire

### 🟠 PRIORITÉ HAUTE
- ARCH-001 : Service Layer + séparation des responsabilités
- ARCH-002 : standardisation des événements WS
- MATCH-001 : refactor du cycle de match
- WS-001 : base WebSocket robuste
- DB-002 : optimiser ORM / N+1
- GQL-001 : sécuriser GraphQL

### 🟡 PRIORITÉ MOYENNE
- OBS-001 : observabilité

### 🟢 PRIORITÉ BASSE
- SCALE-001 : préparation au scaling horizontal

---

## 19. DEFINITION OF DONE

Une amélioration est considérée comme terminée si elle respecte toutes les conditions suivantes :

- [ ] Code implémenté
- [ ] Architecture respectée
- [ ] Design Pattern justifié
- [ ] Sécurité vérifiée
- [ ] Tests ajoutés
- [ ] Tests existants toujours fonctionnels
- [ ] Performance vérifiée si pertinent
- [ ] Documentation mise à jour
- [ ] Logs adaptés
- [ ] Migration vérifiée
- [ ] Aucun comportement existant cassé

---

## 20. RÉSULTAT ATTENDU

Le backend peut évoluer progressivement vers un système :
- plus sécurisé ;
- plus lisible ;
- mieux structuré ;
- plus testable ;
- plus rapide ;
- plus stable temps réel ;
- compatible avec plusieurs instances backend ;
- plus facile à maintenir au fil des évolutions.

L’idée clé est simple :

> ne pas faire de “big bang”, mais améliorer le système par petites étapes, avec tests, validation et mesure.

---

## 21. CONCLUSION

Le backend QuizMada est déjà une base solide avec une bonne séparation fonctionnelle et une présence sérieuse de Redis / Channels / GraphQL / Django. Ce qui manque surtout à ce stade, c’est la consolidation des points critiques :
- stockage des états temporaires ;
- atomicité des transactions wallet / gains ;
- sécurité de production ;
- standardisation des événements temps réel ;
- observabilité ;
- optimisation ORM/GraphQL.

Si ces points sont traités dans l’ordre logique décrit dans ce plan, le backend deviendra beaucoup plus robuste et prêt pour une montée en charge réelle.

---

## 22. NOTE DE CLARTÉ SUR LES INFORMATIONS NON VÉRIFIÉES

Certaines améliorations peuvent dépendre d’éléments non encore visibles dans le repo, ou de la production réelle, par exemple :
- charge réelle du système ;
- configuration de staging/prod exacte ;
- historique des incidents ;
- limite réelle de l’infra ;
- stratégie de monitoring externe.

Ces éléments sont donc marqués ici comme :

> À VÉRIFIER

avant mise en production complète.
