# Intranet DGES

Application intranet Django destinée à la Direction Générale de l'Enseignement Supérieur.

## Objectif de la V1

Cette première version fournit une base stable, légère et démontrable avec :

- authentification Django ;
- gestion des utilisateurs, profils, rôles et groupes ;
- tableau de bord Directeur Général ;
- gestion des visiteurs ;
- suivi des tâches avec liste et vue kanban ;
- programmation des réunions avec notifications internes ;
- gestion documentaire avec upload de fichiers ;
- administration Django ;
- données de démonstration adaptées à la DGES.

## Architecture retenue

Projet Django : `intranet_dges`

Applications :

- `core` : page d'accueil, journal d'activité, utilitaires communs, commande de démonstration ;
- `accounts` : services, profils utilisateurs, rôles, groupes et gestion des comptes ;
- `dashboard` : tableau de bord global et indicateurs ;
- `visitors` : registre des visiteurs et suivi entrée/sortie ;
- `tasks` : tâches, historique et vue kanban ;
- `meetings` : réunions, convocations et compte à rebours ;
- `documents` : documents, upload et archivage ;
- `diplomas` : lots d'arrivée de diplômes, suivi individuel, circuit de signature du DG.

## Base de données

- Développement local : `SQLite`
- Production future : `PostgreSQL`
- Bascule prévue via la variable d'environnement `DATABASE_URL`

Le code reste compatible avec PostgreSQL sans dépendre de SQLite.

## Installation locale

### 1. Créer l'environnement virtuel

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Installer les dépendances

```powershell
pip install -r requirements.txt
```

### 3. Appliquer les migrations

```powershell
python manage.py makemigrations
python manage.py migrate
```

### 4. Créer un superutilisateur

```powershell
python manage.py createsuperuser
```

### 6. Lancer le serveur

```powershell
python manage.py runserver
```

Accès :

- application : `http://127.0.0.1:8000/`
- administration : `http://127.0.0.1:8000/admin/`

## Création des comptes

L'application ne contient **aucun compte ni aucune donnée de démonstration**.
Un compte `dg` au mot de passe connu sur un intranet réel serait une porte ouverte.

1. créez votre compte administrateur avec `python manage.py createsuperuser` ;
2. connectez-vous, créez les services réels de la direction ;
3. créez les comptes des agents depuis **Utilisateurs**, en attribuant à chacun son rôle.

Si une base contient encore des données de démonstration d'une version antérieure :

```powershell
python manage.py purge_demo                # inventaire, ne supprime rien
python manage.py purge_demo --confirmer    # suppression effective
```

La commande refuse de s'exécuter s'il ne resterait aucun superutilisateur après la purge.

## Panneau général d'accès

Réservé à l'administrateur, avec l'annuaire ouvert en lecture au Directeur Général.

- **synthèse** : comptes actifs, comptes désactivés, services, mots de passe en attente
  de changement ;
- **répartition des comptes par rôle**, chaque barre menant à l'annuaire filtré ;
- **tableau des responsabilités** de chaque rôle, reflet de la matrice de `constants.py` ;
- **annuaire filtrable** par rôle et par état ;
- **services** : création, modification, désactivation. Un service auquel des agents sont
  rattachés ne peut pas être supprimé — il faut le désactiver, pour ne pas orpheliner
  les fiches ;
- **réinitialisation de mot de passe** : l'administrateur attribue un mot de passe
  provisoire affiché **une seule fois**, et l'agent est **contraint de le changer** à sa
  prochaine connexion — aucune autre page ne lui est accessible avant ;
- **activation / désactivation** d'un compte sans le supprimer ; l'administrateur ne peut
  ni supprimer ni désactiver son propre compte.

Le changement de son propre mot de passe reste accessible à tout agent depuis
`/accounts/mot-de-passe/`.

## Tableau de bord

- ce qui attend une décision passe en premier : courriers à viser, lots à signer,
  tâches à valider — chaque ligne menant directement à la fiche ;
- le tableau s'adapte au rôle : le DG voit « Courriers à viser » là où le secrétariat
  voit « Courriers à transmettre au DG » ;
- répartitions par étape de circuit, en barres cliquables qui filtrent le registre ;
- sélecteur de période (7 / 30 / 90 jours) dans une rangée unique au-dessus de tout ce
  qu'il cadre ; les files de décision et les alertes montrent l'état courant,
  indépendamment de la période ;
- charge par service, alertes (courriers urgents, anomalies, tâches en retard).

Les graphiques sont en HTML et CSS, sans bibliothèque externe : rien à charger depuis
Internet, ce qui reste compatible avec la politique de sécurité du contenu servie par
Nginx. Une seule teinte de bleu est utilisée, s'assombrissant avec l'avancement dans le
circuit ; les rampes claire et sombre ont été validées contre les surfaces réelles de
l'application (teinte unique, luminosité monotone, contraste suffisant).

## Rôles et matrice de droits

Sept rôles. La règle structurante : **rien n'atteint le bureau du Directeur Général
sans le visa du Secrétariat**, ni pour les courriers ni pour les lots de diplômes.

| Rôle | Responsabilité |
|---|---|
| **Directeur Général** | Validation générale, signature, vue sur toute l'activité |
| **Administrateur** | Création des comptes, distribution des accès, administration technique |
| **Secrétariat** | Déclenche les actions, vise et transmet au DG, tient le planning |
| **Secrétariat adjoint** | Enregistre les visiteurs et les courriers, programme le planning du DG |
| **Service courrier** | Réceptionne et traite le courrier entrant |
| **Agent d'étude** | Vérifie les lots, insère chaque diplôme, valide la conformité |
| **Agent** | Rôle par défaut : ses propres tâches, la documentation partagée |

Capacités et rôles qui les détiennent :

| Capacité | Rôles |
|---|---|
| Voir l'activité de toute la direction | DG, Administrateur |
| Enregistrer les visiteurs | Secrétariat, Secrétariat adjoint, Administrateur |
| Réceptionner et traiter le courrier | Service courrier, Secrétariat adjoint, Administrateur |
| Consulter le registre du courrier | Courrier, Secrétariat adjoint, Secrétariat, DG, Administrateur |
| Déposer et classer un document | Courrier, Secrétariat, Secrétariat adjoint, Administrateur |
| **Transmettre au DG (visa)** | **Secrétariat, Administrateur** |
| **Signer, valider, retourner** | **DG, Administrateur** |
| Gérer les lots et les diplômes | Agent d'étude, Administrateur |
| Consulter le registre des diplômes | Agent d'étude, Secrétariat, DG, Administrateur |
| Tenir le planning de la direction | Secrétariat, Secrétariat adjoint, Administrateur |
| Créer les comptes, distribuer les accès | Administrateur |
| Consulter l'annuaire des comptes | Administrateur, DG |

Cette matrice est définie une seule fois, dans `accounts/constants.py`. Les vues et les
selectors appellent des capacités (`can_transmit_to_dg`, `can_manage_diplomas`…) et jamais
un rôle en dur : réorganiser les rôles ne demande donc pas de revenir sur les gabarits.
Elle est couverte par les tests de `accounts/tests.py`, qui vérifient pour chacun des sept
rôles à la fois ce qui est autorisé **et ce qui doit être refusé**.

## Fonctions déjà disponibles

### Comptes et rôles

- gestion des profils par service ;
- sept rôles, chacun adossé à un groupe Django dont les permissions sont recalculées
  automatiquement ;
- `is_staff` dérivé du rôle : seul l'administrateur accède à l'administration Django ;
- désactivation d'un compte par le drapeau `actif` du profil.

### Tableau de bord

- visiteurs du jour ;
- tâches en attente ;
- documents récents ;
- activités par service ;
- alertes ;
- activités récentes.

### Visiteurs

- ajout ;
- modification ;
- sortie ;
- historique consultable dans la liste.

### Tâches

- chacun gère ses propres tâches ;
- **partage avec d'autres agents** : les agents partagés consultent et font avancer la tâche ;
- la visibilité par service n'accorde pas le droit de modifier — il faut être créateur,
  destinataire, partagé, ou relever du secrétariat ;
- création ;
- affectation ;
- priorités ;
- statuts ;
- historique ;
- vue liste ;
- vue kanban.

### Salles de réunion

- salles créées et modifiées par le secrétariat : nom, localisation, capacité, équipements ;
- une salle décochée « disponible » reste dans l'historique mais n'est plus réservable ;
- écran d'occupation consultable par tous : libre, occupée jusqu'à telle heure, prochaine
  réservation ;
- **détection de conflit à la programmation** : réserver une salle déjà retenue sur le créneau
  est refusé, en nommant la réunion en place et son horaire de fin ;
- une réunion annulée ou déjà tenue libère le créneau ;
- une salle rattachée à des réunions ne peut pas être supprimée — il faut la désactiver, pour
  que l'historique reste lisible.

La durée est saisie en minutes ; c'est elle qui permet de calculer les chevauchements.

### Réunions

- programmation réservée au secrétariat, chargé du personnel, DG et administrateur ;
- date, heure et salle ;
- invitation par agent ou par service ;
- validation de réunion ;
- notifications internes pour les agents concernés ;
- compte à rebours vers la prochaine réunion ;
- vue liste et vue calendrier ;
- affichage clair des réunions du jour et de la semaine ;
- rappels internes automatiques avant réunion ;
- statuts `tenue` et `reportee`.

### Documents

- ajout de document ;
- upload de fichier ;
- classement par type ;
- service concerné ;
- archivage.

### Courriers

Registre du courrier avec circuit de visa imposé. Aucune étape ne peut être sautée.

| Étape | Qui l'exécute |
|---|---|
| Réception et enregistrement (référence `COUR-année-numéro`) | Service courrier, Secrétariat adjoint |
| Prise en traitement | Service courrier |
| Transmission au secrétariat | Service courrier |
| **Visa et transmission au DG** | **Secrétariat** |
| Renvoi au service courrier, motif obligatoire | Secrétariat |
| **Visa avec instruction** | **Directeur Général** |
| Retour au secrétariat, motif obligatoire | Directeur Général |
| Diffusion pour suite à donner | Secrétariat |
| Classement | Service courrier |

- sens entrant ou sortant, priorité normale ou urgente ;
- expéditeur, objet, service destinataire, date de réception et date portée sur le courrier ;
- pièce numérisée téléchargeable via une vue contrôlée, jamais servie en direct ;
- l'instruction du DG est enregistrée avec le visa et redescend au service concerné ;
- notifications internes à chaque changement de main, dédoublonnées par personne ;
- historique complet de chaque mouvement, avec motif ;
- fiche verrouillée dès l'entrée dans le circuit de visa ;
- export CSV du registre, ouvrable dans Excel.

Le service courrier **ne peut pas** saisir directement le bureau du DG : la tentative est
refusée avec un message explicite.

#### Fiche d'analyse du courrier

Reprise du formulaire papier de la DGES.

**Renseigné par le service courrier** : suivi du courrier (référence et date), courrier
arrivée (numéro et date), provenance, objet.

**Renseigné par le Directeur Général** : la grille d'**imputations**, les 12
**instructions** (« Urgence », « Pour suite à donner », « A classer »…), la rubrique
**AUTRES** et ses observations.

- **fiche imprimable** au format de l'imprimé, en-tête ministériel compris : le
  secrétariat l'imprime avant la remise, rubriques du DG laissées vierges pour être
  annotées à la main ;
- **saisie à l'écran** possible pour le DG, ou **report par le secrétariat** quand le DG
  a annoté le papier. L'application enregistre qui a saisi et marque la fiche
  « reportée pour le compte du Directeur Général » — la décision reste celle du DG, la
  frappe est celle de la secrétaire ;
- **cocher une imputation prévient le service ou l'agent visé**, avec les instructions et
  les observations du DG. C'est ce qui remplace la circulation du courrier de bureau en
  bureau ;
- **la grille est construite à partir des services actifs et de leurs agents** : une
  colonne par service, avec « Tout le service » puis chaque agent. Créer un compte ou un
  service suffit à le faire apparaître ; désactiver un service le retire. Aucune liste à
  maintenir en parallèle.

Les 12 instructions de l'imprimé sont amorcées à l'installation et modifiables depuis
l'administration.

#### Donner suite à un courrier

Un agent imputé ne traite pas le courrier lui-même : il **traite la tâche qui en découle**.

- l'agent imputé **voit le courrier** et peut l'ouvrir depuis sa notification ;
- au moment de renseigner la fiche, le DG peut cocher **« Ouvrir une tâche de suivi pour
  chaque imputation »** : chaque agent et chaque service imputé reçoit alors une tâche
  portant l'objet du courrier, les instructions et les observations ;
- la tâche naît **urgente** si le courrier est marqué urgent ou si « Urgence » est coché ;
- quand l'agent fait avancer sa tâche, **l'avancement remonte dans l'historique du
  courrier** : « Suite donnée — tâche … : Validé » ;
- lorsque toutes les tâches sont closes, le courrier porte la mention **« le courrier peut
  être classé »** et le secrétariat en est averti ;
- le **classement** revient au service courrier, au secrétariat ou au Directeur Général.

La fiche du courrier affiche les tâches de suivi, leur destinataire et leur état.

### Lots de diplômes

Module de suivi des diplômes soumis à la signature du Directeur Général.

- registre des lots d'arrivée, filtrable et paginé, avec compteurs par statut ;
- référence automatique `LOT-DIP-année-numéro`, ou saisie manuelle ;
- établissement d'origine, date d'arrivée, nombre annoncé, agent réceptionnaire ;
- écart entre le nombre annoncé et le nombre réellement enregistré, affiché en permanence ;
- saisie des diplômes un par un, ou import d'un fichier `.csv` / `.xlsx` avec aperçu ligne
  par ligne avant enregistrement (aucune écriture avant validation) ;
- signalement d'anomalies : diplôme manquant, erreur de nom, référence incorrecte,
  pièce non conforme ;
- circuit de traitement : reçu → en vérification → conforme → transmis au DG → signé →
  retourné au service → remis → archivé ;
- **la signature et le retour pour correction sont réservés au Directeur Général** ;
- la transmission à la signature est bloquée tant qu'une anomalie subsiste ;
- notifications internes : le DG est prévenu d'un lot à signer, le service est prévenu de
  la signature ou d'un retour pour correction ;
- fiche individuelle par diplôme avec historique complet des actions (preuve de traitement) ;
- recherche transverse par nom, numéro, filière, établissement ou référence de lot ;
- traçabilité du retrait d'un diplôme par son bénéficiaire ;
- exports CSV du registre et des diplômes d'un lot, ouvrables directement dans Excel.

#### Qui peut faire quoi

Chaque étape appartient à un rôle et à un seul. Un agent ne voit à l'écran que les
actions dont il détient la capacité : l'agent d'étude n'aperçoit aucun bouton de
transmission, le secrétariat aucun bouton de signature.

| Étape du circuit | Qui l'exécute |
|---|---|
| Réception du lot, insertion et import des diplômes | Agent d'étude |
| Signalement des anomalies, vérification | Agent d'étude |
| Déclaration de conformité | Agent d'étude |
| **Visa et transmission au DG** | **Secrétariat** |
| **Signature** | **Directeur Général** |
| **Retour pour correction, motif obligatoire** | **Directeur Général** |
| Enregistrement du retour du lot signé au service | Secrétariat |
| Remise aux bénéficiaires, archivage | Agent d'étude |
| Consultation du registre et exports | Agent d'étude, Secrétariat, DG |
| Suppression d'un lot ou d'un diplôme | Administrateur |

L'administrateur détient toutes les capacités ci-dessus.

Deux garde-fous métier s'ajoutent aux droits : la transmission est refusée tant qu'un
diplôme est marqué non conforme, et un lot vide ne peut pas être déclaré conforme.

#### Format du fichier d'import

La première ligne contient les intitulés de colonnes ; l'ordre est libre et les accents,
majuscules et variantes courantes sont reconnus.

| Colonne | Obligatoire | Remarque |
|---|---|---|
| Nom | oui | nom du bénéficiaire |
| Numéro | oui | numéro du diplôme, unique dans le lot |
| Filière | non | |
| Établissement | non | celui du lot par défaut |
| Année | non | année académique, par exemple `2024-2025` |
| Observations | non | |

Les lignes en doublon, sans nom ou sans numéro sont signalées dans l'aperçu et exclues de
l'import ; les autres lignes restent importables.

## Passage futur vers PostgreSQL

Installer PostgreSQL et définir `DATABASE_URL`.

Exemple :

```powershell
$env:DATABASE_URL="postgresql://postgres:motdepasse@localhost:5432/intranet_dges"
python manage.py migrate
```

Le projet utilisera automatiquement PostgreSQL si `DATABASE_URL` est définie.

## Déploiement Docker sur Ubuntu local

La pile de déploiement fournie comprend :

- `web` : application Django servie par Gunicorn ;
- `db` : base PostgreSQL ;
- `nginx` : reverse proxy Nginx exposé sur le réseau local.

### Fichiers ajoutés

- `Dockerfile`
- `docker-compose.yml`
- `docker/entrypoint.sh`
- `docker/nginx/default.conf`
- `.env`
- `.env.example`

### Volumes persistants prévus

- `postgres_data` : données PostgreSQL
- `media_data` : documents et fichiers uploadés
- `static_data` : fichiers statiques collectés

### Variables sensibles

Le fichier `.env` contient les variables suivantes :

```env
SECRET_KEY=replace-this-with-a-long-random-secret-key
DEBUG=0
ALLOWED_HOSTS=localhost,127.0.0.1,192.168.100.5,intranet-dges.local,messagerie.dges.local
POSTGRES_DB=intranet_dges
POSTGRES_USER=intranet_dges_user
POSTGRES_PASSWORD=change-this-postgres-password
NEXTCLOUD_POSTGRES_PASSWORD=change-this-nextcloud-password
DJANGO_SECURE_SSL_REDIRECT=1
SESSION_COOKIE_SECURE=1
CSRF_COOKIE_SECURE=1
INTRANET_URL=https://intranet-dges.local
INTRANET_FALLBACK_URL=https://192.168.100.5
MESSAGING_URL=https://messagerie.dges.local:8443
MESSAGING_FALLBACK_URL=https://192.168.100.5:8443
DOCUMENT_MAX_UPLOAD_SIZE=20971520
DOCUMENT_ALLOWED_EXTENSIONS=pdf,doc,docx,xls,xlsx,csv,txt,png,jpg,jpeg,odt,ods
```

Avant le déploiement réel, remplacer :

- `SECRET_KEY` par une clé Django longue et aléatoire ;
- `ALLOWED_HOSTS` par `localhost,127.0.0.1,IP_DU_SERVEUR`;
- `POSTGRES_PASSWORD` et `NEXTCLOUD_POSTGRES_PASSWORD` par des mots de passe robustes ;
- `INTRANET_FALLBACK_URL` et `MESSAGING_FALLBACK_URL` par l'IP réelle du serveur ;
- `SECURE_HSTS_SECONDS` uniquement après validation complète du HTTPS interne.

### Lancement sur Ubuntu

```bash
docker compose up -d --build
```

### Initialisation de l'application

Une fois les conteneurs démarrés :

```bash
docker compose exec web python manage.py createsuperuser
```

Le conteneur `web` applique automatiquement :

- les migrations ;
- `collectstatic` ;
- le lancement de Gunicorn sur `0.0.0.0:8000`.

### Accès réseau local

Depuis le serveur Ubuntu :

- `https://127.0.0.1/`
- `https://intranet-dges.local/`

Depuis un poste du réseau local :

- `https://IP_DU_SERVEUR/`
- `https://intranet-dges.local/`
- `https://messagerie.dges.local:8443/`

Condition importante :

- ouvrir les ports `80`, `443` et `8443` sur le serveur Ubuntu si un pare-feu est actif ;
- renseigner cette même IP dans `ALLOWED_HOSTS`.

### Résolution du nom local `intranet-dges.local`

Pour que `intranet-dges.local` fonctionne sur le réseau local, il faut une résolution de nom.

Option simple pour les postes de test :

- ajouter dans le fichier `hosts` de chaque poste l'entrée `IP_DU_SERVEUR intranet-dges.local`
- ajouter aussi `IP_DU_SERVEUR messagerie.dges.local` pour Nextcloud Talk

Exemple Windows :

```text
192.168.100.5 intranet-dges.local
192.168.100.5 messagerie.dges.local
```

Exemple Ubuntu :

```bash
echo "192.168.100.5 intranet-dges.local" | sudo tee -a /etc/hosts
echo "192.168.100.5 messagerie.dges.local" | sudo tee -a /etc/hosts
```

Option plus propre à l'échelle du réseau :

- créer une entrée DNS locale sur le routeur ou le serveur DNS interne.

Note :

- `.local` fonctionne, mais peut parfois entrer en concurrence avec le mécanisme mDNS ; si cela devient gênant, `intranet-dges.lan` sera plus prévisible.

### Services Docker

```bash
docker compose ps
docker compose logs -f web
docker compose logs -f nginx
docker compose logs -f db
```

### Arrêt

```bash
docker compose down
```

Pour arrêter sans perdre les données persistantes, ne pas supprimer les volumes Docker.

## Sauvegarde automatique

Un service Docker dédié (`backup`) réalise **une sauvegarde par jour**, sans intervention.

Il tourne dans Docker plutôt que dans le planificateur Windows pour une raison précise :
Docker Desktop s'exécute dans la session de l'utilisateur, et une tâche planifiée Windows
échouerait silencieusement session fermée. Un service Docker, lui, repart avec la pile
après un redémarrage. Et si Docker est arrêté, l'application l'est aussi : aucune donnée
ne change.

### Ce qui est sauvegardé

Chaque nuit, dans un sous-dossier horodaté **créé automatiquement** :

| Fichier | Contenu |
|---|---|
| `intranet-postgres.sql.gz` | base de l'application |
| `nextcloud-postgres.sql.gz` | base de la messagerie |
| `media.tar.gz` | pièces jointes : documents, courriers, diplômes |
| `MANIFESTE.txt` | contenu, tailles et commandes de restauration |

Une sauvegarde interrompue est renommée avec le suffixe **`_INCOMPLETE`** : une sauvegarde
partielle qu'on croit valable est plus dangereuse qu'une absence de sauvegarde.

### Une sauvegarde manquée est rattrapée

Le planificateur ne compte pas le temps restant jusqu'à l'heure fixée : il **compare la
date réelle** toutes les cinq minutes, et sauvegarde dès qu'un nouveau jour est entamé et
que l'heure cible est passée.

La distinction est loin d'être théorique. Un simple « dormir jusqu'à 1h00 » échoue dès que
la machine se met en veille : le conteneur est gelé, le compte à rebours s'arrête avec
lui, et la sauvegarde de la nuit est perdue sans que personne ne s'en aperçoive. Avec la
comparaison de date, **un poste rallumé à 8h00 rattrape immédiatement la sauvegarde de la
nuit**, et le journal l'indique explicitement :

```
planificateur : sauvegarde de 1h non effectuée (machine éteinte ou en veille) : rattrapage
```

Le repère de la dernière sauvegarde est écrit dans `.derniere-sauvegarde`, à la racine du
dossier de destination : il survit au redémarrage du conteneur comme à celui de la
machine, et empêche une seconde sauvegarde le même jour.

### Réglages (`.env`)

| Variable | Rôle | Défaut |
|---|---|---|
| `BACKUP_DIR` | destination sur la machine hôte | `./sauvegardes` |
| `BACKUP_HOUR` | heure de déclenchement (0–23) | `1` |
| `BACKUP_RETENTION_DAYS` | jours conservés, `0` désactive la purge | `14` |
| `BACKUP_INCLUDE_NEXTCLOUD_FILES` | inclure les fichiers Nextcloud (volumineux) | `0` |
| `BACKUP_ON_START` | sauvegarder au démarrage du conteneur | `0` |

**Placez `BACKUP_DIR` sur le second disque** : une sauvegarde sur le même disque que la
base ne protège de rien en cas de panne matérielle.

```env
BACKUP_DIR=D:/sauvegardes-intranet-dges
```

Si Docker ne parvient pas à créer le dossier, créez-le une fois à la main.

### Vérifier et déclencher à la main

```powershell
docker compose logs backup                              # journal et prochaine échéance
docker compose exec backup /usr/local/bin/sauvegarde.sh # sauvegarde immédiate
```

### Restaurer

**La base de l'application :**

```powershell
docker compose exec -T db psql -U intranet_dges_user -d postgres -c "DROP DATABASE intranet_dges;"
docker compose exec -T db psql -U intranet_dges_user -d postgres -c "CREATE DATABASE intranet_dges;"
gzip -dc sauvegardes\2026-08-03_21h35\intranet-postgres.sql.gz | docker compose exec -T db psql -U intranet_dges_user -d intranet_dges
docker compose restart web
```

**Les pièces jointes :**

```powershell
docker run --rm -v v1_media_data:/media -v "${PWD}\sauvegardes\2026-08-03_21h35:/sauvegarde" alpine sh -c "cd /media && tar -xzf /sauvegarde/media.tar.gz"
```

**Essayez la restauration sans rien casser** — restaurez dans une base d'essai et comparez
les compteurs :

```powershell
docker compose exec -T db psql -U intranet_dges_user -d postgres -c "CREATE DATABASE essai_restauration;"
gzip -dc sauvegardes\...\intranet-postgres.sql.gz | docker compose exec -T db psql -U intranet_dges_user -d essai_restauration
docker compose exec -T db psql -U intranet_dges_user -d essai_restauration -c "select count(*) from courriers_courrier;"
docker compose exec -T db psql -U intranet_dges_user -d postgres -c "DROP DATABASE essai_restauration;"
```

Cette procédure a été exécutée : la base restaurée présentait exactement les mêmes
volumes que la base vivante, contenu compris.

## Journalisation et historique des connexions

**Journal applicatif.** Deux destinations : la sortie standard, que Docker capture
(`docker compose logs -f web`), et un fichier tournant `logs/intranet.log` (5 Mo, 5
rotations). Le niveau se règle par `DJANGO_LOG_LEVEL`, le répertoire par
`DJANGO_LOG_DIR`. Si le répertoire n'est pas créable, l'application démarre quand même
avec la seule sortie standard plutôt que de refuser de se lancer.

**Historique des connexions**, consultable par l'administrateur et le DG depuis le
panneau d'accès :

- réussites, échecs et déconnexions ;
- identifiant tapé conservé même quand le compte n'existe pas — une série d'échecs sur
  un même nom est le premier signe d'essais successifs ;
- adresse d'origine réelle : derrière Nginx, `REMOTE_ADDR` est celle du proxy, donc on
  retient la première adresse de `X-Forwarded-For` ;
- navigateur et système déclarés par le poste ;
- filtrage par résultat, recherche par identifiant ou adresse, compteurs sur 24 heures.

**Démarrage protégé.** Si `DEBUG=0` et que `SECRET_KEY` porte encore la valeur de
développement, l'application refuse de démarrer avec un message explicite. Auparavant
elle se lançait silencieusement avec une clé connue.

## Points de sécurité déjà pris en charge

- documents téléchargés via Django avec contrôle d'accès, et non plus servis directement depuis `/media/` ;
- formulaires de création et modification des documents limités aux profils autorisés ;
- sortie visiteur protégée en `POST` avec jeton CSRF ;
- redirections `next` assainies pour éviter les renvois vers des URL externes ;
- cookies de session sécurisables via `.env` et redirection HTTPS prévue derrière Nginx ;
- types de fichiers et taille d'upload contrôlés côté serveur ;
- interface Bootstrap servie localement, sans dépendance Internet pour l'affichage.

## Disponibilite quotidienne

En pratique, pour que le serveur soit disponible chaque jour :

1. le serveur Ubuntu reste allume dans la salle serveur ;
2. Docker demarre automatiquement avec Ubuntu ;
3. le service `systemd` `intranet-dges.service` relance `docker compose up -d` apres chaque redemarrage ;
4. `nginx` expose l'intranet sur le reseau local ;
5. les agents utilisent toujours le meme lien.

Le fichier `deploy/systemd/intranet-dges.service` est fourni pour cela.

Installation du demarrage automatique sur Ubuntu :

```bash
sudo cp deploy/systemd/intranet-dges.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable docker
sudo systemctl enable intranet-dges
sudo systemctl start intranet-dges
```

Verification :

```bash
sudo systemctl status intranet-dges
docker compose ps
```

Un guide d'exploitation plus detaille est disponible dans :

- `docs/EXPLOITATION.md`

## Recommandations de déploiement V2

- servir Bootstrap localement au lieu d'un CDN ;
- ajouter sauvegardes automatiques ;
- renforcer la journalisation ;
- ajouter module courriers ;
- ajouter demandes internes et notifications ;
- prévoir reverse proxy et HTTPS interne ;
- tester les droits par profil de manière plus fine.
