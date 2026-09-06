# Feuille de route — Backend Quizz Web Madagascar

Ordre recommandé de développement. Chaque étape doit être testée (tests unitaires
minimum sur `wallet` et `betting`) avant de passer à la suivante.

## Étape 0 — Socle du projet

- [ ] Initialiser le projet Django en mode ASGI (`django-admin startproject config`).
- [ ] Mettre en place l'arborescence complète du projet (voir `README.md` §
      "Structure du projet") : `apps/`, `schema/`, `common/`, `infra/`.
- [ ] Configurer `settings/base.py`, `settings/dev.py`, `settings/staging.py`,
      `settings/prod.py`.
- [ ] Ajouter Strawberry (`strawberry-graphql-django`) et créer le endpoint `/graphql/`.
- [ ] Configurer Django Channels (`asgi.py`, `channels_redis` comme channel layer).
- [ ] Mettre en place Docker Compose : `backend`, `postgres`, `redis`, `nginx`.
- [ ] Configurer `django-environ` pour la gestion des variables d'environnement.
- [ ] Mettre en place `django-cors-headers` (liste blanche stricte des origines).
- [ ] Configurer les logs structurés (JSON) + intégration Sentry.

## Étape 1 — Utilisateurs & Authentification (RG-USR)

- [ ] Modèle `Utilisateur` (extension de `AbstractUser` ou modèle custom) :
      pseudo unique, email unique, code_parrain, code_parent, ville_origine.
- [ ] Génération automatique du code parrain à l'inscription (RG-USR-02).
- [ ] Upload Photo de Profil / Photo de Couverture (stockage S3-compatible recommandé).
- [ ] Mutation GraphQL `register`, `login`.
- [ ] Implémenter JWT maison : access token (courte durée, en mémoire côté client),
      refresh token (cookie httpOnly, Secure, SameSite=None, rotation à chaque usage).
- [ ] Table `RefreshToken` avec statut révoqué + expiration.
- [ ] Intégrer OAuth2 (`django-allauth` ou `social-auth-app-django`) pour login social.
- [ ] Statut en ligne/hors ligne en temps réel (via Channels, mise à jour à la connexion
      WebSocket).
- [ ] Query `profil` avec statistiques (parties jouées, victoires, défaites, taux de
      réussite, cumul des gains) — calculées ou mises en cache.

## Étape 2 — Portefeuille & Sécurité financière (RG-CPT)

⚠️ Étape critique — voir `BONNE_PRATIQUE.md` avant de commencer.

- [ ] Modèle `Portefeuille` (solde_recharge, solde_gains) lié 1-1 à `Utilisateur`.
- [ ] Modèle `LedgerEntry` (grand livre append-only : type de mouvement, montant,
      référence, timestamp, statut) — source de vérité, jamais d'écriture directe
      sur les soldes sans passer par le ledger.
- [ ] Intégration Mobile Money (MVola, Orange Money, Airtel Money) :
      - Endpoint de dépôt + vérification de signature webhook (HMAC).
      - Traitement asynchrone via Celery (queue `payments`, idempotent).
- [ ] Mutation `demanderRetrait` avec vérification OTP obligatoire (step-up auth).
- [ ] Verrouillage pessimiste (`select_for_update`) sur toute opération de solde,
      dans une transaction atomique.
- [ ] Idempotency-Key obligatoire sur les mutations financières.
- [ ] Tests de concurrence (deux requêtes simultanées ne doivent jamais désynchroniser
      le solde).

## Étape 3 — Réseau social & discussions (RG-SOC / RG-DIS)

- [ ] Fil d'actualité : publications (texte/photo), commentaires, réactions.
- [ ] Système d'invitations : demandes d'amis (par pseudo ou code parrain),
      accepter/refuser, défis de jeu.
- [ ] Salons de discussion par ville (Channels — un groupe WebSocket par ville).
- [ ] Liste des utilisateurs actifs par ville en temps réel.
- [ ] Modération : signalement, suppression de contenu (droits admin).

## Étape 4 — Thèmes & Questions (base du moteur de jeu)

- [ ] Modèles `Theme`, `Question`, `Reponse` (RG : min. 4 réponses, 1 correcte, 3 fausses).
- [ ] CRUD admin pour créer/valider les questions (RG-GAM admin).
- [ ] Import en masse de questions (script de seed pour Culture, Musique, Ohabolana...).

## Étape 5 — Moteur de match temps réel (RG-GAM)

- [ ] Modèle `Match` (type_jeu, mise, score_final cible), `Tour`, `Participation`.
- [ ] Mutation `creerPartie` (choix thème + score cible) → statut "En attente".
- [ ] Mutation `rejoindrePartie` → verrouillage de la mise des deux joueurs
      (création d'entrées ledger "mise bloquée").
- [ ] Consumer Channels dédié au match : gestion des phases (Lecture 5s / Réponse 5s)
      via `asyncio` timers côté serveur (source de vérité du temps, jamais le client).
- [ ] Logique de "première bonne réponse marque le point" + passage de main
      automatique (RG-GAM-03).
- [ ] Variante "L'Intrus" (défaite instantanée si mauvais choix) (RG-GAM-04).
- [ ] Détection de victoire (score cible atteint) → clôture du match, crédit des gains
      moins commission (5-10%) via le ledger, dans une transaction atomique.
- [ ] Gestion de l'abandon / déconnexion — règle dépendant du moment dans le match :
      - **Avant le 1er tiers du score cible** (ex: < 2 pts sur un match en 8 pts,
        alignement avec le seuil de clôture des paris RG-BET-02) : délai de grâce
        court (ex: 30s) pour reconnexion, puis **annulation du match + remboursement
        intégral des deux mises** (les paris spectateurs déjà placés sont aussi
        remboursés, cf. RG-BET-03).
      - **Après le 1er tiers** : délai de grâce identique, puis **victoire par
        forfait de l'adversaire encore connecté** (le pot des mises lui est
        crédité, commission plateforme appliquée comme une victoire normale).
      - Le délai de grâce est géré côté serveur (tâche Celery différée ou timer
        Channels), jamais côté client.
      - Distinguer déconnexion réseau (retry autorisé) d'un abandon explicite
        (quitter la partie → forfait immédiat, sans délai de grâce).

## Étape 6 — Mode spectateur & paris en direct (RG-SPC / RG-BET)

- [ ] Rejoindre un match en cours en tant que spectateur (lecture seule, diffusion
      Channels du match, aucune interférence possible).
- [ ] Mutation `placerPari` (mise sur un joueur, prélevée du solde_recharge) —
      avec step-up auth (OTP) comme pour les autres opérations financières.
- [ ] Clôture des paris dès qu'un joueur atteint le premier tiers du score cible
      (RG-BET-02).
- [ ] Résolution des paris à la fin du match : gain crédité (mise × cote) sur
      solde_gains, ou perte définitive, ou remboursement intégral si match annulé
      (RG-BET-03) — via tâche Celery déclenchée à la clôture du match.
- [ ] **Anti-fraude / collusion — règles simples (MVP)** :
      - Interdire à un utilisateur de parier sur un match où il est lui-même
        joueur.
      - Interdire de parier sur le match d'un filleul direct (`code_parent`
        pointant vers l'utilisateur) et réciproquement (parrain).
      - Interdire à deux comptes créés depuis la même IP/appareil dans une
        fenêtre de temps courte de parier l'un sur l'autre (vérification simple
        à l'inscription : empreinte appareil basique + IP).
      - Ces contrôles sont appliqués comme des validations bloquantes dans la
        mutation `placerPari`.
- [ ] **Anti-fraude — préparer la détection avancée (post-MVP)** :
      - Prévoir dès maintenant l'enregistrement des métadonnées utiles
        (IP, user-agent, empreinte appareil, timestamps précis des réponses)
        dans le ledger/logs, même sans les exploiter tout de suite.
      - Poser la structure d'une table `SignalFraude` (type d'anomalie,
        utilisateurs concernés, score de suspicion, statut de revue) qui sera
        alimentée plus tard par des règles ou un modèle de scoring
        (temps de réponse anormalement constants, taux de victoire suspect
        entre deux mêmes comptes, etc.).
      - Ne pas bloquer automatiquement sur cette détection avancée au départ :
        alimenter une file de revue manuelle pour l'admin.

## Étape 7 — Limitation de quota & Rate limiting

Deux objectifs distincts à traiter ensemble : **anti-fraude** sur les actions
sensibles et **maîtrise des coûts d'infrastructure** sur les requêtes lourdes.

- [ ] Mettre en place un middleware/extension Strawberry de rate limiting basé
      sur Redis (compteur glissant, type `django-ratelimit` ou implémentation
      custom avec `redis-py`).
- [ ] **Quotas anti-fraude** (par utilisateur ET par IP, les deux dimensions) :
      - `login` : ex. 5 tentatives / 15 min, puis verrouillage progressif
        (backoff exponentiel) + captcha après plusieurs échecs.
      - `placerPari` : ex. limite de nombre de paris par match et par fenêtre de
        temps, pour éviter le martelage automatisé.
      - `demanderRetrait` : ex. 1 demande active à la fois par utilisateur,
        limite quotidienne de tentatives OTP.
      - `register` : limite de créations de compte par IP/jour (lutte contre
        les faux comptes de filleuls pour abuser du parrainage).
- [ ] **Quotas coûts d'infra** (protection des requêtes GraphQL lourdes) :
      - Query complexity limiting sur le schéma Strawberry (score max par
        requête, ex. calculé sur la profondeur × nombre de champs demandés).
      - Query depth limiting (profondeur max, ex. 8-10 niveaux).
      - Limite de requêtes GraphQL globales par utilisateur/IP par minute
        (au-delà des quotas spécifiques par mutation ci-dessus), pour couvrir
        les queries de lecture (fil d'actualité, historique de match, etc.).
      - Pagination obligatoire sur toutes les listes (fil d'actualité,
        messages de salon, historique de transactions) — jamais de requête
        non bornée.
      - Timeout serveur explicite sur les résolveurs coûteux (ex. stats
        agrégées) + mise en cache Redis des résultats peu volatils.
- [ ] Réponses de dépassement de quota normalisées (code d'erreur GraphQL
      dédié `RATE_LIMITED`, avec `retry_after` indiqué) pour que le frontend
      puisse afficher un message clair plutôt qu'une erreur générique.
- [ ] Journaliser les dépassements de quota répétés comme signal d'entrée dans
      la table `SignalFraude` (lien avec l'étape 6).

## Étape 8 — Durcissement sécurité GraphQL & API

- [ ] Permissions au niveau resolver (rôle + propriété de la ressource).
- [ ] Désactivation de l'introspection GraphQL en production.
- [ ] Audit des CORS, cookies (Secure, HttpOnly, SameSite), headers de sécurité
      (CSP, HSTS via Nginx).
- [ ] Mettre en place le registre central des codes d'erreur
      (`common/graphql/errors.py`) : exceptions métier par domaine
      (`AUTH_*`, `WALLET_*`, `BET_*`, `MATCH_*`, `VALIDATION_*`) + handler
      GraphQL central qui les convertit en `extensions.code` normalisé.
- [ ] Handler d'exception générique : toute exception non prévue renvoie
      `INTERNAL_ERROR` (message générique) côté client, détail complet
      (stack trace) uniquement en logs serveur/Sentry avec `correlation_id`.
- [ ] Vérifier l'absence de fuite d'information sur les erreurs d'auth
      (pas d'énumération de comptes via `login`) et sur les erreurs
      financières/anti-fraude (pas de détail sur les règles internes).
- [ ] Documenter le registre de codes d'erreur pour l'équipe frontend
      (table code → message UX attendu).
- [ ] Tests unitaires sur chaque exception métier (code + absence de fuite)
      et sur le comportement `INTERNAL_ERROR`.

## Étape 9 — Observabilité & déploiement production

- [ ] Pipeline CI (lint, tests, scan de dépendances) avant déploiement.
- [ ] Configuration Nginx + Let's Encrypt (TLS).
- [ ] Firewall (`ufw`), `fail2ban` sur le VPS.
- [ ] Sauvegardes automatisées PostgreSQL (cron + stockage offsite).
- [ ] Monitoring Sentry + logs centralisés.
- [ ] Documentation API (schéma GraphQL exporté, changelog).

## Étape 10 — Menu À Propos & finitions (RG-INF)

- [ ] Pages/queries statiques : règles des jeux, CGU, politique de confidentialité,
      guide du portefeuille électronique.
- [ ] Revue finale de sécurité avant mise en production (checklist `BONNE_PRATIQUE.md`).