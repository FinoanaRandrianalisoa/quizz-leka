# Backend QuizMada — Explication générale

Ce document présente le backend du projet de manière claire et structurielle. Il sert de guide de compréhension pour savoir comment l’application est organisée, comment les données circulent et quelles responsabilités ont les différents modules.

## 1. Vue d’ensemble

Le backend est une application Django moderne avec :
- Django pour la logique applicative, les modèles, les vues et les API
- GraphQL pour l’API principale (via Strawberry)
- Django Channels pour les WebSockets temps réel
- PostgreSQL / base relationnelle pour le stockage
- Celery pour certaines tâches asynchrones
- JWT pour l’authentification

Le projet est pensé comme une plateforme de jeux en ligne : quiz, défis, communauté, wallet, notifications, parties multijoueurs, etc.

Le backend est donc bien plus qu’un simple service de données : il gère également le jeu en temps réel, la logique de scores, les notifications, les transactions monétaires, les messages, les demandes d’amis, et la synchronisation WebSocket.

---

## 2. Structure principale

La structure du dossier backend est organisée par domaines fonctionnels.

### Dossier principal

- `apps/` : contient les modules applicatifs
- `config/` : configuration Django et ASGI/WSGI
- `schema/` : schéma GraphQL global
- `common/` : utilitaires et composants transverses
- `requirements/` : dépendances Python

### Modules applicatifs

Les modules principaux dans `Back/apps/` sont :

- `auth/` : authentification, JWT, middleware, permissions, OTP
- `users/` : profil utilisateur, rôles, gestion des comptes
- `themes/` : thèmes, questions, réponses
- `matches/` : création de parties, tours, réponses, logique des quiz multijoueurs
- `betting/` : paris et gestion de paris autour des matchs
- `social/` : publications, réactions, commentaires, amis, notifications
- `discussions/` : salons de discussion, messages en temps réel
- `wallet/` : portefeuille, gains, transactions
- `moderation/` : modération et supervision
- `betting/` : prises de paris, résultats, gestion de mises

Chaque module suit généralement la même logique :
- `models.py` : modèles de données
- `queries.py` : requêtes GraphQL
- `mutations.py` : mutations GraphQL
- `services.py` : logique métier
- `types.py` : types GraphQL exposés
- `tests/` : tests unitaires et fonctionnels

---

## 3. Le cœur Django

### 3.1. `config/settings/`

C’est le dossier de configuration Django. Il contient les paramètres du projet :
- base de données
- middlewares
- applications installées
- sécurité
- fichiers media
- JWT
- Channels
- Celery
- services externes (Redis, etc.)

Les fichiers de settings peuvent distinguer plusieurs environnements :
- `base.py` pour la configuration commune
- `dev.py` / `prod.py` / `testing.py` selon l’environnement

Cela permet d’avoir le même code mais des paramètres adaptés selon le contexte.

### 3.2. `config/asgi.py` et `config/routing.py`

Le backend utilise ASGI pour le support WebSocket.

- `asgi.py` : démarre l’application ASGI Django
- `routing.py` : mappe les routes WebSocket vers leurs consumers

Exemples de flux temps réel :
- notifications par utilisateur
- salons de discussion
- parties en cours
- défis RPS multijoueurs

---

## 4. Authentification et sécurité

### `apps/auth/`

Ce module contient tout le système d’authentification.

Il gère typiquement :
- inscription
- connexion
- génération de JWT
- refresh token / gestion session
- permissions
- middleware d’authentification
- OTP pour sécurité supplémentaire
- backends personnalisés

### Middleware JWT

Le projet n’utilise pas seulement Django au sens classique : il impose une couche d’authentification JWT pour les appels GraphQL et les WebSockets.

Cela permet :
- vérifier les utilisateurs dans les mutations
- sécuriser les endpoints GraphQL
- identifier les joueurs connectés pour les messages temps réel

Le module `common/graphql/permissions.py` ou équivalent est central pour charger l’utilisateur courant à partir du contexte GraphQL.

---

## 5. Modèle des utilisateurs

### `apps/users/`

Le modèle utilisateur centralise :
- email
- pseudo
- photo de profil
- ville d’origine
- rôle (admin / joueur / autres selon le projet)
- statut en ligne
- parrainage / code parrain
- associations sociales

Ce module participe aussi à :
- gestion des profils
- statistiques
- classements
- rôles d’administration

La logique utilisateur est utilisée partout : dans les parties, les notifications, les demandes d’amis, les messages, le wallet, etc.

---

## 6. Les thèmes et les questions

### `apps/themes/`

La logique des quiz est basée sur les thèmes et les questions.

Les éléments principaux sont :
- `Theme` : catégorie / sujet du quiz
- `Question` : question posée au joueur
- `Reponse` : choix de réponse

Le système permet :
- ajouter des thèmes
- créer des questions
- associer plusieurs réponses
- marquer la bonne réponse
- valider ou non une question
- charger des questions par thème

La génération des tours de partie dépend de cette couche : une partie de quiz va choisir une question dans le thème demandé, puis attendre la réponse du joueur.

---

## 7. Les parties et le moteur de jeu

### `apps/matches/`

C’est probablement le module le plus central du backend.

Il gère la mécanique des jeux et des parties.

#### Modèles principaux
- `Match` : une partie entre deux joueurs / participants
- `Participation` : relation entre un utilisateur et une partie
- `Tour` : un round dans une partie
- `ReponseTour` : réponse donnée par un joueur à un tour

#### Logique métier
Ce module gère :
- création d’une partie
- invitation / acceptation d’un autre joueur
- enchaînement des tours
- calcul du score
- détermination du vainqueur
- clôture d’une partie
- fin de match
- broadcasting temps réel à travers les WebSockets

#### Services de jeu
Les services font le trou entre les mutations GraphQL, les modèles et le diffuseur WebSocket.

Par exemple :
- `creer_partie(...)`
- `rejoindre_partie(...)`
- `soumettre_reponse(...)`
- `annuler_partie(...)`

Les fonctions peuvent aussi envoyer des événements à un groupe socket pour notifier les joueurs d’une mise à jour :
- nouvelle question
- score modifié
- match terminé
- tour suivant

#### Match multijoueur et live
Le match n’est pas seulement un objet database : il est aussi un flux live.

Le backend diffuse des événements via Channels, par exemple :
- `match_<id>`
- `notifications_<user_id>`
- groupes pour des salons, parties ou défis

Cela permet que les joueurs voient la partie évoluer sans recharger la page.

---

## 8. Le jeu RPS (Pierre / Papier / Ciseaux)

### `apps/matches/services.py`

Les défis RPS sont gérés dans le même module de matches, mais de manière spéciale.

Le backend maintient des structures mémoire :
- `RPS_CHALLENGES` : défis en attente
- `RPS_MATCHES` : parties déjà acceptées

Ces structures servent à gérer le rythme ultra-léger des défis en direct.

Le flux est généralement :
1. joueur A défie joueur B
2. backend crée un challenge temporaire
3. joueur B reçoit une notification
4. joueur B accepte le défi
5. backend crée une partie RPS active
6. chaque joueur envoie un coup
7. backend compare les coups et détermine le gagnant

Il s’agit d’un système “éphémère” plus simple qu’un match traditionnel de quiz, car il ne repose pas sur une base de données de tour/score longue durée, mais sur des objets en mémoire adaptés au défi rapide.

---

## 9. GraphQL

### `schema/schema.py`

Le schéma GraphQL global réunit les queries et mutations de tous les modules.

On y trouve :
- `Query` : lecture des données
- `Mutation` : opérations de modification

Exemple de logique :
- `login` ou `register`
- `creerPartie`
- `rejoindrePartie`
- `soumettreReponse`
- `defierJoueurRps`
- `accepterDefiRps`
- `jouerCoupRps`
- `publier`, `commenter`, etc.

### `queries.py` et `mutations.py`

Chaque application expose :
- les requêtes disponibles
- les mutations disponibles
- les types GraphQL associés

Les `types.py` servent à exposer les objets de domaine à GraphQL :
- `MatchType`
- `UtilisateurType`
- `NotificationType`
- `PublicationType`
- `RpsChallengeType`
- `RpsMatchType`

Cela permet d’avoir une API standardisée et bien structurée.

---

## 10. Notifications et social

### `apps/social/`

Ce module traite le social de la plateforme :
- publications
- commentaires
- réactions
- demandes d’amis
- notifications

#### `Notification`
Le modèle de notification représente un événement important pour un utilisateur, par exemple :
- défi reçu
- défi accepté
- demande d’ami acceptée
- message système

Chaque notification contient :
- `destinataire`
- `type`
- `titre`
- `message`
- `reference_id`
- `lu`

#### `services.py`
La fonction `envoyer_notification(...)` a un rôle crucial :
- crée la notification en base
- l’envoie à un groupe WebSocket dédié
- permet au frontend de recevoir la notification en temps réel

Cela est essentiel pour les cas comme :
- défi reçu
- invitation d’ami
- mise à jour de statut

---

## 11. Discussions en temps réel

### `apps/discussions/`

Le module de discussions gère les salons de discussion par ville ou par communauté.

Le consommateur WebSocket `NotificationConsumer` et les autres consumers permettent :
- se connecter à un salon de ville
- envoyer des messages en temps réel
- diffuser les messages à tous les utilisateurs du salon

Le cœur est le même que pour les notifications : les groupes Channels permettent de transmettre les messages sans rechargement de page.

---

## 12. Wallet et transactions

### `apps/wallet/`

Le portefeuille est un module très important pour les jeux avec mises, gains et récompenses.

Il gère :
- solde du joueur
- crédit/débit
- historique de transactions
- gains en fonction des matchs
- commissions éventuelles

Le wallet est souvent appelé après la fin d’une partie ou d’un défi :
- victoire => gain
- match annulé => remboursement
- paris résolus => distribution

Cela relie le gameplay au système financier de la plateforme.

---

## 13. Betting / paris

### `apps/betting/`

Le système de paris est un domaine spécifique :
- les utilisateurs peuvent miser sur un match
- les résultats sont traités automatiquement
- la plateforme répartit les gains et les commissions

Le module reçoit souvent un signal lors de la fin d’un match pour calculer les gains. Cela montre le côté “plateforme de jeux” du projet, où le backend n’est pas seulement un jeu simple, mais un système complet avec économie virtuelle et jeux compétitifs.

---

## 14. Les WebSockets et Channels

### Pourquoi c’est important
Le backend est conçu pour la synchronisation en direct.

Les WebSockets sont utilisés pour :
- les notifications
- les messages
- les salons de discussion
- les matchs en cours
- les défis RPS

Les groupes sociaux sous `channel_layer.group_send(...)` permettent de notifier des utilisateurs précis ou des groupes entiers sans passer par la base de données à chaque instant.

Cela donne au frontend une expérience fluide :
- pas de rafraîchissement manuel
- mise à jour de score live
- notification immédiate
- partie en cours synchronisée

---

## 15. La logique de test

### `apps/.../tests/`

Le backend contient des tests pour vérifier les comportements métier de base.

Les tests couvrent typiquement :
- création d’une partie
- réponse correcte / incorrecte
- fin d’un match
- défi RPS
- notification envoyée à la bonne personne
- validation des permissions

Les tests sont essentiels pour garantir que les changements ne cassent pas la logique de jeux et de sécurité.

---

## 16. Le flux typique d’une action utilisateur

Voici la logique générale d’un cas d’utilisation classique :

### Cas : un joueur crée une partie
1. le frontend envoie une mutation GraphQL
2. le backend vérifie l’utilisateur courant
3. le service crée un `Match` en base
4. le backend associe les participants
5. le service ouvre le premier tour ou prépare le match
6. le backend diffuse un message WebSocket à l’autre joueur
7. le frontend met à jour l’interface

### Cas : un joueur défie un autre en RPS
1. le frontend appelle `defierJoueurRps`
2. le backend crée un challenge dans `RPS_CHALLENGES`
3. le backend envoie une notification à la cible
4. le destinataire reçoit l’événement notifié via WebSocket
5. il clique sur la notification
6. le backend accepte le défi via `accepterDefiRps`
7. une partie RPS est créée
8. la page du duel s’ouvre et les coups peuvent être envoyés

---

## 17. Points forts du backend

Le backend de ce projet est robuste parce qu’il mélange plusieurs aspects :
- logique de jeu
- logique de communauté
- logique financière
- gestion des temps réels
- synchronisation multi-utilisateur
- API sécurisée

C’est un backend de type “plateforme gaming social” plutôt qu’un simple service CRUD.

---

## 18. Conclusion

Le backend est construit autour de 4 grands axes :

1. Gestion des utilisateurs et sécurité
2. Gestion des jeux et des scores
3. Gestion sociale et notifications
4. Synchronisation live avec WebSocket

Ces axes travaillent ensemble pour donner une plateforme complète, avec :
- quiz en multijoueur
- défis temps réel
- interactions sociales
- portefeuille et gains
- communication instantanée

En somme, le backend est le moteur central du projet : il valide les actions, calcule les résultats, tient les données cohérentes et diffuse les évolutions en temps réel aux utilisateurs.
