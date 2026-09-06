# Bonnes pratiques & Sécurité — Backend Quizz Web Madagascar

Ce document liste les règles **non négociables** pour ce projet, vu la présence
d'argent réel (mises, paris, retraits Mobile Money). À relire avant toute mise en
production et à chaque revue de code touchant `wallet`, `betting` ou `auth`.

---

## 1. Authentification & sessions

- **Access token JWT** : durée de vie courte (10–15 min), stocké **en mémoire
  JavaScript côté React** — jamais dans `localStorage` ou `sessionStorage`
  (vulnérable au XSS).
- **Refresh token** : cookie `HttpOnly`, `Secure`, `SameSite=None` (domaines
  séparés `app.quizz.mg` / `api.quizz.mg`), scopé au path `/api/auth/refresh/`
  uniquement. **Rotation à chaque utilisation** + table `RefreshToken` permettant
  la révocation immédiate (déconnexion, compromission suspectée).
- **CORS** : `CORS_ALLOWED_ORIGINS` en liste blanche explicite. Ne jamais utiliser
  `CORS_ALLOW_ALL_ORIGINS = True`. `CORS_ALLOW_CREDENTIALS = True` requis pour les
  cookies cross-site.
- **OAuth2 / social login** : ne jamais faire confiance à l'email retourné par le
  provider sans vérifier son statut "vérifié" (`email_verified`).
- **Mots de passe** : hashage Argon2 (`django.contrib.auth.hashers.Argon2PasswordHasher`
  en premier dans `PASSWORD_HASHERS`), politique de complexité minimale, jamais de
  mot de passe en clair dans les logs.

## 2. Step-up authentication (opérations financières)

Toute mutation touchant l'argent (`demanderRetrait`, `placerPari`, `effectuerDepot`
si applicable) exige une **vérification renforcée**, en plus du JWT standard :

- OTP envoyé par SMS (Mobile Money / provider tiers type Twilio ou Africa's Talking).
- Token éphémère généré après validation OTP, **usage unique**, durée de vie ≤ 5 min.
- Ne jamais réutiliser le même OTP/token pour deux opérations différentes.
- Journaliser (audit log) chaque tentative réussie/échouée avec horodatage et IP.

## 3. Transactions financières & portefeuille

- **`DecimalField` obligatoire** pour tout montant. Jamais de `FloatField` (erreurs
  d'arrondi inacceptables sur de l'argent réel).
- **Grand livre append-only (ledger)** : chaque mouvement (dépôt, mise bloquée, gain
  crédité, commission plateforme, retrait, remboursement) crée une entrée immuable.
  Le solde affiché est dérivé du ledger, jamais modifié directement en place.
- **Verrouillage pessimiste** : toute lecture-modification-écriture d'un solde passe
  par `Model.objects.select_for_update()` à l'intérieur d'un bloc
  `transaction.atomic()`. Aucune exception.
- **Idempotency-Key** obligatoire sur les mutations de dépôt/retrait/mise — un même
  clic ou un retry réseau ne doit jamais créditer/débiter deux fois.
- **Vérification de signature HMAC** sur tous les webhooks Mobile Money (MVola,
  Orange Money, Airtel Money) avant tout traitement. Rejeter silencieusement (log +
  alerte) toute requête non signée correctement.
- **Commission de plateforme** calculée et enregistrée comme une ligne de ledger à
  part entière (traçabilité comptable).
- Tests de **concurrence obligatoires** (deux requêtes simultanées sur le même
  portefeuille) avant toute mise en production d'une fonctionnalité financière.

## 4. Sécurité spécifique GraphQL

- **Query depth limiting** et **complexity limiting** activés sur le schéma
  Strawberry — sans ça, une requête imbriquée malveillante peut saturer la base.
- **Introspection désactivée en production** (`__schema`, `__type` bloqués hors
  environnement de développement).
- **Permissions au niveau du resolver**, jamais uniquement au niveau du schéma :
  chaque champ/mutation vérifie le rôle (`ADMIN` vs `JOUEUR`) **et** la propriété
  de la ressource (un joueur ne peut lire/modifier que son propre portefeuille,
  profil, etc.).
- Envisager les **persisted queries** côté client pour fermer la surface
  d'attaque (le client envoie un hash pré-enregistré, pas la requête brute).
- Ne jamais renvoyer de messages d'erreur détaillés (stack trace, requête SQL) au
  client en production — logger côté serveur, renvoyer un message générique.
- **Pagination obligatoire** sur toute liste (fil d'actualité, historique de
  transactions, messages de salon) — aucune query GraphQL ne doit pouvoir
  renvoyer un volume non borné.

## 5. Limitation de quota & Rate limiting

Deux finalités à traiter distinctement, avec des règles différentes :

**a) Anti-fraude (par utilisateur ET par IP)**

| Action              | Limite indicative                          |
|---------------------|---------------------------------------------|
| `login`              | 5 tentatives / 15 min, backoff exponentiel, captcha après échecs répétés |
| `register`           | Limite de créations de compte par IP/jour (anti faux-comptes de parrainage) |
| `placerPari`         | Limite de paris par match et par fenêtre de temps (anti martelage) |
| `demanderRetrait`    | 1 demande active à la fois, limite quotidienne de tentatives OTP |

- Implémenté via compteur glissant Redis (`django-ratelimit` ou extension
  Strawberry custom), jamais en mémoire locale du process (ne tient pas la
  charge en multi-instance).
- Un dépassement répété de quota alimente le signal de suspicion (voir §8
  Anti-fraude paris) plutôt que d'être simplement ignoré.

**b) Maîtrise des coûts d'infrastructure**

- Limite de requêtes GraphQL globales par utilisateur/IP par minute, en plus
  des quotas spécifiques ci-dessus (couvre les queries de lecture coûteuses).
- Timeout serveur explicite sur les résolveurs lourds (stats agrégées,
  historiques) + cache Redis sur les résultats peu volatils.
- Réponse de dépassement normalisée : code d'erreur GraphQL dédié
  `RATE_LIMITED` avec `retry_after`, pour que le frontend affiche un message
  clair plutôt qu'une erreur générique.

## 6. Temps réel (Django Channels)

- Le **serveur est la seule source de vérité pour le temps** (minuteurs 5s/5s) —
  ne jamais faire confiance à un timer côté client.
- Vérifier l'authentification à l'établissement de la connexion WebSocket
  (middleware Channels dédié, basé sur le JWT).
- Les spectateurs ont un accès **strictement lecture seule** au flux du match —
  vérifier côté serveur qu'aucune action de jeu n'est acceptée depuis un rôle
  spectateur, même si le client tente de l'envoyer.
- Isoler les groupes Channels par match/ville (`match_<id>`, `ville_<id>`) pour
  éviter les fuites d'information entre parties/salons.

## 7. Infrastructure & déploiement (VPS)

- **TLS obligatoire** partout (Let's Encrypt/certbot, renouvellement automatisé),
  `SECURE_SSL_REDIRECT = True`, HSTS activé.
- **Firewall** (`ufw`) : n'ouvrir que 80/443/22. **fail2ban** sur SSH.
- **Redis et PostgreSQL** jamais exposés sur une interface publique — réseau
  Docker interne uniquement, mot de passe fort sur Redis (`requirepass`).
- **Secrets** via variables d'environnement (`django-environ`), jamais commités.
  Un fichier `.env.example` sans valeurs réelles sert de référence. En production,
  privilégier un vault ou des secrets chiffrés (ex: `sops`, secrets Docker).
- `DEBUG = False` non négociable en production, `ALLOWED_HOSTS` strict.
- **Sauvegardes PostgreSQL automatisées** (cron `pg_dump`) + copie offsite —
  critique vu les données financières et le ledger.
- **Monitoring** : Sentry pour les exceptions, logs structurés JSON, alerte sur
  échec de webhook de paiement ou pic d'erreurs sur `wallet`/`betting`.
- **Celery** : files séparées par priorité (`payments` en priorité haute avec
  retry/backoff exponentiel, `notifications`, `default`). Idempotence des tâches
  (un webhook rejoué ne doit pas produire d'effet en double).

## 8. Anti-fraude sur les paris (collusion entre comptes)

**Règles simples, actives dès le MVP** (bloquantes dans la mutation
`placerPari`) :

- Un utilisateur ne peut pas parier sur un match où il est lui-même joueur.
- Interdiction de parier sur le match d'un filleul direct (`code_parent`
  pointant vers l'utilisateur) et réciproquement (parrain → filleul).
- Deux comptes créés depuis la même IP/empreinte appareil dans une fenêtre de
  temps courte ne peuvent pas parier l'un sur l'autre.

**Préparer la détection avancée (post-MVP), sans bloquer automatiquement** :

- Enregistrer dès maintenant les métadonnées utiles (IP, user-agent, empreinte
  appareil, timestamps précis de réponse) même sans les exploiter tout de
  suite — les reconstruire après coup depuis des logs incomplets est
  impossible.
- Table `SignalFraude` (type d'anomalie, comptes concernés, score de
  suspicion, statut de revue) alimentée par des règles simples au départ
  (temps de réponse anormalement constants, taux de victoire répété entre les
  deux mêmes comptes), avec revue manuelle admin plutôt que blocage auto.

## 9. Résilience du moteur de match (déconnexion / abandon)

La règle dépend du **moment du match**, alignée sur le seuil de clôture des
paris (RG-BET-02, premier tiers du score cible) :

- **Avant le premier tiers** : délai de grâce court pour reconnexion, puis
  **annulation du match + remboursement intégral** des deux mises et des paris
  spectateurs déjà placés.
- **Après le premier tiers** : délai de grâce identique, puis **victoire par
  forfait** de l'adversaire encore connecté (pot des mises crédité, commission
  plateforme appliquée normalement).
- Distinguer une **déconnexion réseau** (retry/reconnexion autorisée pendant
  le délai de grâce) d'un **abandon explicite** (quitter la partie → forfait
  immédiat, sans délai de grâce).
- Le délai de grâce est toujours piloté **côté serveur** (timer Channels ou
  tâche Celery différée), jamais côté client.
- À la reconnexion, le client **resynchronise l'état complet du match** depuis
  le serveur (source de vérité unique) plutôt que de repartir sur un état
  supposé.

## 10. Gestion des codes d'erreur

Sur une API financière, une erreur mal gérée peut soit **fuiter de l'information
sensible**, soit **laisser le frontend dans un état ambigu** (l'utilisateur ne
sait pas si son retrait a été pris en compte). Les règles ci-dessous s'appliquent
à toute mutation/query du schéma GraphQL.

**a) Format normalisé**

Toute erreur métier renvoyée par une mutation/query suit une structure fixe
via les `extensions` GraphQL (Strawberry) :

```json
{
  "message": "Solde insuffisant pour effectuer ce pari.",
  "extensions": {
    "code": "WALLET_INSUFFICIENT_FUNDS",
    "correlation_id": "a1b2c3d4",
    "retry_after": null
  }
}
```

- `code` : identifiant stable, en `SCREAMING_SNAKE_CASE`, préfixé par domaine
  (`AUTH_`, `WALLET_`, `BET_`, `MATCH_`, `SOCIAL_`, `VALIDATION_`,
  `RATE_LIMITED`). Le frontend se base **sur ce code**, jamais sur le texte du
  `message` (qui peut changer ou être traduit).
- `message` : lisible par un humain, en français, sans terme technique
  (pas de nom de champ Django, pas de trace SQL).
- `correlation_id` : identifiant unique de la requête, permettant de retrouver
  l'erreur exacte dans les logs serveur/Sentry sans exposer de détail au client.
- `retry_after` : présent uniquement pour les erreurs de quota (`RATE_LIMITED`).

**b) Taxonomie des erreurs — deux catégories strictement séparées**

- **Erreurs métier attendues** (solde insuffisant, OTP invalide, pari déjà
  clôturé, quota dépassé) : exceptions custom dédiées par domaine
  (`InsufficientFundsError`, `InvalidOtpError`, `BetAlreadyClosedError`...),
  capturées par un handler GraphQL central qui les convertit en `extensions.code`
  connu. Ce sont des cas normaux du métier, **pas des bugs** — donc pas
  d'alerte Sentry bruyante dessus.
- **Erreurs techniques inattendues** (bug, exception non prévue, timeout DB) :
  toujours renvoyées au client sous un code générique unique
  `INTERNAL_ERROR`, message générique ("Une erreur est survenue, veuillez
  réessayer."). Le détail complet (stack trace, requête SQL) part **uniquement**
  dans les logs serveur + Sentry, jamais dans la réponse GraphQL.

**c) Registre central des codes**

- Un seul fichier `common/graphql/errors.py` définit toutes les exceptions
  métier et leur code associé — pas de code d'erreur "en dur" créé à la volée
  dans un resolver. Toute nouvelle erreur métier doit être ajoutée à ce
  registre avant d'être utilisée.
- Documenter ce registre (table code → signification → code HTTP GraphQL —
  toujours 200 pour GraphQL, l'échec se lit dans `errors[]`) pour que
  l'équipe frontend puisse mapper chaque code à un message traduit/UX
  spécifique, sans dépendre du texte serveur.

**d) Anti-fuite d'information**

- Erreurs d'authentification génériques : `login` renvoie toujours
  `AUTH_INVALID_CREDENTIALS` que ce soit l'email qui n'existe pas ou le mot de
  passe qui est faux — ne jamais permettre l'énumération de comptes existants.
- Idem pour `demanderRetrait`/`placerPari` : ne pas révéler dans le message
  d'erreur des détails internes (ex. seuils exacts de détection de fraude,
  structure de la table `SignalFraude`).
- Aucune erreur ne doit jamais inclure : requête SQL, chemin de fichier
  serveur, nom de variable interne, stack trace, ou détail d'implémentation
  d'un provider tiers (Mobile Money, OTP).

**e) Cohérence avec le rate limiting et les webhooks**

- Le code `RATE_LIMITED` (voir §5) suit le même format que les erreurs métier —
  pas un format ad hoc.
- Les webhooks Mobile Money (REST, pas GraphQL) suivent leur propre convention
  HTTP standard (4xx si signature invalide/payload malformé, 5xx si erreur
  serveur, 200 dès que le webhook est accepté pour traitement asynchrone même
  si le traitement métier n'est pas encore terminé) — ne pas mélanger les
  deux conventions dans `wallet/webhooks.py`.

**f) Tests**

- Chaque exception métier du registre a un test unitaire vérifiant qu'elle
  produit bien le `code` attendu et un `message` sans fuite de détail
  technique.
- Test de non-régression sur `INTERNAL_ERROR` : une exception Python non
  prévue levée dans un resolver ne doit jamais remonter son message brut au
  client (test qui simule une exception inattendue et vérifie la réponse).

## 11. Qualité de code & process

- Tests unitaires **obligatoires** sur `wallet`, `betting`, `auth` avant toute
  fusion sur la branche principale.
- Revue de code systématique sur toute modification touchant l'argent ou
  l'authentification (double validation, pas de merge solo).
- Pipeline CI : lint (`ruff`/`flake8`), tests, scan de dépendances
  (`pip-audit` ou équivalent) avant déploiement.
- Ne jamais logger de données sensibles (mots de passe, tokens, OTP, numéros
  Mobile Money complets — masquer partiellement si besoin de traçabilité).

## Checklist avant mise en production

- [ ] `DEBUG = False`, introspection GraphQL désactivée
- [ ] TLS actif, HSTS activé
- [ ] CORS en liste blanche stricte
- [ ] Cookies refresh token : `HttpOnly`, `Secure`, `SameSite` corrects
- [ ] OTP fonctionnel sur toutes les mutations financières
- [ ] Ledger financier testé en situation de concurrence
- [ ] Webhooks Mobile Money : signature vérifiée
- [ ] Rate limiting actif sur `login`, `register`, `placerPari`, `demanderRetrait`
- [ ] Quota global de requêtes GraphQL par utilisateur/IP en place
- [ ] Règles anti-fraude simples actives sur `placerPari` (auto-pari, filleul direct, IP/appareil partagé)
- [ ] Règle de gestion de la déconnexion en match testée (avant/après 1er tiers)
- [ ] Registre central des codes d'erreur (`common/graphql/errors.py`) à jour et documenté
- [ ] Aucun message d'erreur ne fuit de détail technique (stack trace, SQL, chemin serveur)
- [ ] `INTERNAL_ERROR` générique testé sur exception inattendue
- [ ] Sauvegardes PostgreSQL automatisées et testées (restauration validée)
- [ ] Sentry/monitoring actif
- [ ] Firewall + fail2ban configurés sur le VPS