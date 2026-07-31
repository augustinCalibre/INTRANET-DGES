# Architecture technique - Messagerie interne locale DGES

## 1. Objet

Ce document propose une architecture simple, locale et maintenable pour ajouter une messagerie interne avec appels audio/video a l'intranet DGES.

Le besoin n'est pas un chatbot. Le besoin est :

- messagerie entre agents ;
- groupes par service ;
- appels audio ;
- appels video ;
- partage de fichiers ;
- acces navigateur ;
- acces telephone sur le Wi-Fi interne ;
- stockage 100% local sur le serveur Ubuntu.

## 2. Recommandation executive

### Recommandation MVP

Pour la DGES, la meilleure base de depart est :

- `Nextcloud + Nextcloud Talk`
- avec `PostgreSQL` dedie a Nextcloud
- `Redis` pour le cache et le verrouillage
- `coturn` local pour fiabiliser WebRTC
- le `Nginx` local existant comme reverse proxy

### Pourquoi ce choix

Cette option couvre en une seule plateforme :

- chat interne ;
- audio/video ;
- fichiers ;
- groupes ;
- acces web et mobile ;
- fonctionnement local sans cloud.

Elle est plus simple a maintenir que :

- `Rocket.Chat + Jitsi + MongoDB + apps marketplace`
- `Mattermost + Jitsi + plugins/licence + stack supplementaire`

## 3. Comparaison rapide

### A. Nextcloud + Talk

Points forts :

- chat, appels et fichiers dans une seule solution ;
- tres bon fit pour un intranet administratif ;
- navigateur + mobile ;
- PostgreSQL supporte ;
- Redis recommande ;
- integration naturelle avec la gestion documentaire et les groupes.

Points faibles :

- l'interface est plus "suite collaborative" que "chat pur" ;
- pour les appels de groupe frequents, le HPB Talk devient utile ;
- il faut du HTTPS interne pour camera/micro.

Verdict :

- meilleur choix pour une V1 DGES.

### B. Rocket.Chat + Jitsi local

Points forts :

- tres bon outil de chat temps reel ;
- Jitsi apporte la video ;
- deployment Docker bien documente.

Points faibles :

- plus de briques a exploiter ;
- MongoDB en plus ;
- la video depend d'une app/provider separe ;
- la doc officielle Rocket.Chat prevoit des apps marketplace et des points de contact cloud ;
- en mode air-gapped, le plan Starter demande une validation periodique hors-ligne.

Verdict :

- bon choix si la priorite absolue est le chat type "Slack", moins bon pour une V1 administrative simple.

### C. Mattermost + Jitsi local

Points forts :

- tres robuste en self-hosted ;
- bon produit pour chat d'equipe et exploitation ;
- bon positionnement souverain / reseaux fermes.

Points faibles :

- les appels natifs auto-heberges sont presentes surtout comme audio + partage d'ecran ;
- pour la video, on retombe sur une integration externe comme Jitsi ;
- la pile devient plus complexe pour un besoin de 12 agents ;
- certaines fonctions avancees sont liees a des editions/licences.

Verdict :

- excellent pour un usage operations/chatops, moins adapte qu'un Nextcloud Talk pour la DGES en V1.

## 4. Architecture cible recommandee

## 4.1 Vue d'ensemble

```text
Postes agents / telephones Wi-Fi
            |
            v
      Nginx reverse proxy local
      - intranet.dges.local
      - messagerie.dges.local
            |
            +--> Django intranet + Gunicorn
            |        |
            |        +--> PostgreSQL intranet
            |
            +--> Nextcloud Apache
                     |
                     +--> PostgreSQL Nextcloud
                     +--> Redis
                     +--> Nextcloud Talk
                     +--> coturn (STUN/TURN)
```

## 4.2 Positionnement des composants

### Intranet Django

- conserve son stack actuelle ;
- reste separe de la messagerie ;
- peut ajouter plus tard un lien "Messagerie interne" ;
- peut pousser plus tard du provisioning utilisateurs.

### Nextcloud

- application distincte ;
- sous-domaine distinct `messagerie.dges.local` ;
- base de donnees dediee ;
- stockage des fichiers dedie ;
- groupes par service : DG, Secretariat, Courrier, Planification, Informatique, etc.

### Redis

- necessaire/recommande pour Nextcloud ;
- ameliore les performances ;
- evite les problemes de file locking.

### coturn

- recommande des le depart si on veut fiabiliser les appels depuis le Wi-Fi, les mobiles et certains navigateurs ;
- les flux restent locaux au serveur local ;
- ne passe pas par un service tiers.

### HPB Nextcloud Talk

- non retenu dans le MVP ;
- a activer si la DGES fait souvent des appels de groupe ou des reunions video a plus de 4 participants actifs ;
- a planifier comme `Phase 2`.

## 5. Pourquoi je ne mets pas le HPB dans le MVP

Pour 12 agents, la V1 la plus robuste est :

- Nextcloud Talk standard ;
- Redis ;
- coturn ;
- sans HPB.

Raison :

- moins de complexite ;
- moins de maintenance ;
- moins de risque de panne ;
- plus rapide a deployer.

Le HPB Talk devient pertinent quand :

- les reunions video de groupe deviennent frequentes ;
- on veut une meilleure qualite au-dela de 4 participants actifs ;
- on veut plus de charge simultanee.

## 6. Services Docker a prevoir

## 6.1 Services MVP

- `intranet-db` : PostgreSQL pour Django
- `intranet-web` : Django + Gunicorn
- `nginx` : reverse proxy local pour les deux applications
- `nextcloud-db` : PostgreSQL pour Nextcloud
- `nextcloud-redis` : cache/verrouillage Nextcloud
- `nextcloud-app` : Nextcloud Apache
- `nextcloud-cron` : taches de fond Nextcloud
- `coturn` : serveur TURN/STUN local

## 6.2 Services optionnels Phase 2

- `talk-hpb-signaling`
- `talk-hpb-janus`
- eventuellement un bus interne selon le mode de packaging HPB retenu

## 7. Structure de fichiers conseillee

```text
intranet-dges/
├── docker-compose.yml
├── .env
├── docker/
│   └── nginx/
│       └── default.conf
├── deploy/
│   ├── systemd/
│   │   └── intranet-dges.service
│   └── messaging/
│       ├── docker-compose.messaging.example.yml
│       ├── .env.messaging.example
│       ├── nginx/
│       │   └── dges-local.conf
│       └── coturn/
│           └── turnserver.conf
├── docs/
│   ├── EXPLOITATION.md
│   └── ARCHITECTURE_MESSAGERIE_INTERNE.md
└── scripts/
    └── ubuntu/
        └── backup-intranet-dges.sh
```

## 8. Strategie d'authentification

### Option recommandee pour le MVP

Comptes separes au depart.

Pourquoi :

- plus simple ;
- plus rapide ;
- moins de couplage ;
- moins de risques sur le lancement.

Bonnes pratiques MVP :

- garder les memes identifiants fonctionnels que dans Django ;
- meme convention de login ;
- meme liste de services/groupes ;
- procedure simple d'onboarding/offboarding.

### Option preparee pour plus tard

Connexion unique via annuaire central.

Deux trajectoires raisonnables :

- `LDAP/AD` si la DGES met en place un annuaire local ;
- `OIDC/SSO` via un IdP local type Keycloak plus tard.

Preparation conseillee des maintenant :

- usernames stables ;
- emails internes propres ;
- groupes/services normalises ;
- pas de logique metier dependante de mots de passe partages.

## 9. Acces reseau local

## 9.1 Noms internes

Cibles demandees :

- `intranet.dges.local`
- `messagerie.dges.local`

Possible, mais avec une reserve :

- le suffixe `.local` peut entrer en conflit avec le mecanisme mDNS de certains postes.

Recommandation pratique :

- si vous avez un DNS local maitrise : `intranet.dges.local` et `messagerie.dges.local`
- sinon, pour une meilleure prevision reseau : `intranet.dges.lan` et `messagerie.dges.lan`

## 9.2 HTTPS interne

Pour les appels audio/video, il faut traiter les deux noms comme des sites securises.

En pratique :

- certificat interne avec SAN pour les deux noms ;
- installation du certificat racine interne sur les PC et telephones ;
- Nginx en HTTPS devant Django et Nextcloud.

## 10. Variables d'environnement a prevoir

Voir le fichier :

- `deploy/messaging/.env.messaging.example`

Variables principales :

- Django : secret, debug, hosts, DB
- Nextcloud : image, admin, domaines, DB, Redis, limites upload
- coturn : secret, realm, plage de ports
- reseau local : IP serveur, noms internes

## 11. Volumes persistants

## 11.1 Intranet Django

- base PostgreSQL intranet
- media Django
- static Django

## 11.2 Nextcloud

- base PostgreSQL Nextcloud
- volume principal Nextcloud
- config Nextcloud
- custom apps
- data Nextcloud

## 11.3 Logs

Option simple :

- utiliser les logs Docker pour l'applicatif ;
- volume ou bind mount pour les logs Nginx si besoin.

## 12. Strategie de sauvegarde locale

## 12.1 Ce qu'il faut sauvegarder

Minimum :

- dump PostgreSQL intranet ;
- dump PostgreSQL Nextcloud ;
- fichiers Django `media` ;
- fichiers Nextcloud `data` ;
- config Nextcloud ;
- fichiers de deploiement : `docker-compose`, `.env`, `nginx`, `coturn`, scripts.

## 12.2 Frequence recommandee

- dump DB chaque jour
- fichiers chaque jour
- copie de configuration a chaque changement
- retention 14 a 30 jours

## 12.3 Methode simple

1. `pg_dump` pour les deux PostgreSQL
2. archive `tar.gz` pour Django media et volumes Nextcloud
3. copie des fichiers `deploy/`, `.env`, scripts
4. stockage sur :
   - disque local secondaire
   - puis copie periodique sur disque USB admin

## 12.4 Restauration

Il faut savoir restaurer :

1. le `docker-compose`
2. le `.env`
3. les volumes
4. les dumps PostgreSQL

Tester une restauration avant production.

## 13. Limites techniques a anticiper

## 13.1 Nombre d'utilisateurs

Avec 12 agents :

- chat : aucun probleme sur un serveur local correct ;
- appels audio : aucun probleme ;
- visio 1:1 et petits groupes : acceptable ;
- grandes reunions video : a surveiller.

## 13.2 Sans HPB

Ordre de grandeur prudent :

- 1:1 audio/video : OK
- petit groupe 3 a 4 participants : OK si postes et Wi-Fi corrects
- au-dela : qualite moins previsible

## 13.3 Avec HPB

- meilleure tenue des appels de groupe ;
- meilleur comportement quand plusieurs agents participent a la meme reunion ;
- plus de charge serveur et plus de complexite.

## 13.4 PC anciens

Les postes Dual Core anciens sont acceptables pour :

- chat ;
- fichiers ;
- audio ;
- video occasionnelle en petit groupe.

Ils seront plus limites pour :

- video HD ;
- multi-participants ;
- partage d'ecran + camera + autres onglets ouverts.

## 13.5 Wi-Fi

Le point critique n'est pas la connexion Internet a 37 Mbps.

Le point critique est :

- la qualite du LAN ;
- la qualite du Wi-Fi ;
- la couverture ;
- la saturation des bornes ;
- la separation ou non du Wi-Fi invite.

Pour la visio :

- prioriser le Wi-Fi interne bureautique ;
- eviter la visioconference sur le Wi-Fi invite ;
- tester les appels depuis plusieurs zones du batiment.

## 13.6 Serveur

Pour le MVP, viser au minimum :

- 4 vCPU
- 8 Go RAM
- SSD

Plus confortable :

- 8 vCPU
- 16 Go RAM

Surtout si le meme serveur heberge :

- Django ;
- Nextcloud ;
- PostgreSQL x2 ;
- Redis ;
- coturn ;
- Nginx.

## 14. Recommandation finale

### Version MVP recommandee

- garder Django actuel ;
- ajouter Nextcloud + Talk ;
- ajouter PostgreSQL dedie ;
- ajouter Redis ;
- ajouter coturn ;
- reverse proxy Nginx local ;
- comptes separes au depart ;
- pas de HPB en V1.

### Version evoluee

- activer HPB Talk si les reunions video deviennent frequentes ;
- centraliser l'authentification via LDAP ou Keycloak ;
- ajouter sauvegarde automatisee complete ;
- ajouter supervision ;
- ajouter distribution certifiee du certificat interne sur mobiles.

### Ce qu'il faut eviter

- developper une messagerie maison en Django ;
- lancer Rocket.Chat ou Mattermost + Jitsi pour seulement 12 agents sans besoin fort de chat "temps reel pur" ;
- demarrer directement avec SSO + HPB + mobile MDM + federation ;
- rester en HTTP pour les appels audio/video ;
- melanger les bases de donnees intranet et Nextcloud.

## 15. Checklist de deploiement Ubuntu Server

### Preparation

- Ubuntu Server a jour
- Docker Engine
- Docker Compose v2
- horloge systeme correcte
- DNS local ou fichier hosts
- certificat interne pret
- stockage SSD disponible

### Deploiement

1. Copier le projet sur le serveur
2. Copier `deploy/messaging/.env.messaging.example` vers `deploy/messaging/.env`
3. Ajuster mots de passe, IP, domaines
4. Installer les certificats dans `deploy/messaging/nginx/certs/`
5. Verifier la config TURN
6. Lancer :

```bash
docker compose -f deploy/messaging/docker-compose.messaging.example.yml --env-file deploy/messaging/.env up -d --build
```

7. Initialiser Django si necessaire
8. Finaliser Nextcloud
9. Activer l'app Talk si necessaire
10. Configurer le TURN dans l'admin Nextcloud Talk
11. Creer les groupes/services
12. Tester depuis PC et telephone

## 16. Checklist de tests fonctionnels

### Acces

- ouverture de `https://intranet.dges.local`
- ouverture de `https://messagerie.dges.local`
- certificat accepte sur PC
- certificat accepte sur telephone

### Utilisateurs

- connexion utilisateur
- creation d'un utilisateur test
- creation d'un groupe/service
- ajout d'un utilisateur dans un groupe

### Messagerie

- envoi message utilisateur a utilisateur
- creation d'une conversation de groupe
- envoi fichier
- consultation de l'historique

### Appels

- appel audio 1:1
- appel video 1:1
- appel groupe 3 personnes
- appel depuis telephone sur Wi-Fi interne
- verification micro/camera

### Reseau

- fonctionnement sans Internet
- resolution DNS/hosts locale
- acces uniquement depuis LAN/Wi-Fi interne
- impossibilite d'acces depuis un reseau externe non autorise

### Performance

- test sur PC ancien
- test sur un poste recent
- test depuis deux zones Wi-Fi differentes
- test upload fichier de 50 a 100 Mo

## 17. Fichiers fournis

- `docs/ARCHITECTURE_MESSAGERIE_INTERNE.md`
- `deploy/messaging/docker-compose.messaging.example.yml`
- `deploy/messaging/.env.messaging.example`
- `deploy/messaging/nginx/dges-local.conf`
- `deploy/messaging/coturn/turnserver.conf`

## 18. Sources officielles a relire avant production

- Docker Hub Nextcloud official image
- Nextcloud Admin Manual
- Nextcloud Talk documentation
- Rocket.Chat deployment and air-gapped documentation
- Mattermost deployment and calls documentation
