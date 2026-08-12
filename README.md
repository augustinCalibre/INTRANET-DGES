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

### Import de l'annuaire réel

L'état du personnel de la DGES est transcrit dans
[accounts/annuaire_dges.py](accounts/annuaire_dges.py) : huit services, quatorze agents,
avec fonction, rôle, service, adresse et téléphone. Une commande crée le tout :

```powershell
docker compose exec web python manage.py importer_annuaire
```

Elle est faite pour être relancée : elle ne crée que ce qui manque, ne supprime rien, et
**ne rétablit pas le mot de passe d'un compte existant** — un agent qui a choisi le sien
ne doit pas le voir revenir au mot de passe commun à chaque exécution. L'option
`--reinitialiser-mots-de-passe` force ce rétablissement, à n'utiliser qu'avant la
première distribution des accès.

Les services absents de l'organigramme sont **désactivés et non supprimés** : un courrier
imputé à un service disparu doit rester lisible.

Le mot de passe initial est commun et vaut pour l'intranet comme pour la messagerie.
Chaque agent doit le changer à sa première connexion, et son nouveau mot de passe est
porté aux deux systèmes. Il fait dix caractères au minimum, longueur exigée par la
politique de mots de passe de Nextcloud.

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

- **sens** entrant ou sortant, et **nature** du document : courrier simple, autorisation,
  note, ordre de mission. Deux champs distincts et non un seul, parce qu'ils répondent à
  deux questions : le sens fonde les registres arrivée et départ, la nature dit de quel
  document il s'agit. Un ordre de mission peut entrer comme sortir ;
- priorité normale ou urgente ;
- objet, date de réception et date portée sur le courrier ;
- **décharge imprimable** pour les courriers sortants (voir plus bas) ;
- pièce numérisée téléchargeable via une vue contrôlée, jamais servie en direct ;
- l'instruction du DG est enregistrée avec le visa et redescend au service concerné ;
- notifications internes à chaque changement de main, dédoublonnées par personne ;
- historique complet de chaque mouvement, avec motif ;
- fiche verrouillée dès l'entrée dans le circuit de visa ;
- export CSV du registre, ouvrable dans Excel.

Le service courrier **ne peut pas** saisir directement le bureau du DG : la tentative est
refusée avec un message explicite.

#### Entrant et sortant : deux lectures en miroir

Les deux sens ne se remplissent pas de la même façon, et le formulaire n'affiche que les
rubriques du sens choisi.

| | Vient de | Va vers |
|---|---|---|
| **Entrant** | expéditeur, organisme extérieur | service destinataire, interne |
| **Sortant** | service émetteur, interne | destinataire, organisme extérieur |

Le registre, la recherche et l'export lisent les deux de la même manière, par les
colonnes **Provenance** et **Destinataire**.

**Le répertoire des correspondants externes se constitue à l'usage.** À la saisie d'un
courrier sortant, on tape les premières lettres du destinataire : les organismes déjà
utilisés sont proposés, et un nom inédit crée sa fiche automatiquement. Personne n'a de
liste à tenir à jour.

Les noms sont rapprochés sur une forme normalisée — accents retirés, casse ignorée,
espaces réduits. Sans cela, « Universite FHB » et « Université F.H.B. » deviendraient
deux organismes distincts et aucun regroupement ne serait possible six mois plus tard.

#### Décharge de courrier administratif

**Elle ne concerne que les courriers sortants.** Elle part avec le courrier et revient
signée : c'est le destinataire, à l'extérieur de la DGES, qui la remplit à la remise. Un
courrier entrant n'en a pas — la DGES le reçoit, elle ne le remet à personne.

Elle porte son propre numéro, `DECH-année-numéro`, dérivé de la référence du courrier
plutôt que stocké : deux impressions du même courrier portent le même numéro, et une
décharge égarée se réimprime à l'identique.

La page sépare nettement deux blocs, et cette séparation est le cœur du document :

- **le courrier remis**, ce que la DGES atteste en imprimant — numéro de décharge,
  référence, objet, service émetteur, destinataire, date du courrier ;
- **reçu par le destinataire**, ce qu'il atteste en signant — date et heure de réception,
  nom et fonction, nombre de pièces reçues, observations, signature et cachet.

Rien du second bloc n'est pré-rempli. Ni le réceptionnaire ni la date de réception ne
sont connus à l'impression : les porter reviendrait à attester de faits qui ne se sont pas
encore produits, sur un document qui fait preuve.

Comme la fiche d'analyse, la décharge est une page A4 mise en forme pour le papier : le
navigateur l'imprime ou l'enregistre en PDF sans réglage particulier.

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

> **La plateforme fonctionne actuellement en local uniquement.** Les ports
> n'écoutent que sur `127.0.0.1` : rien n'est joignable depuis le réseau, quelles que
> soient les règles du pare-feu. L'accès se fait sur `https://localhost/` et
> `https://localhost:8443/` depuis la machine elle-même.
>
> Ce qui suit décrit l'exposition réseau, conservée pour le jour où elle sera reprise.
> La marche à suivre pour rouvrir l'accès est dans
> [docs/DEPLOIEMENT_WINDOWS_LOCAL.md](docs/DEPLOIEMENT_WINDOWS_LOCAL.md), section
> « Revenir à l'exposition réseau ».

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

Chaque nuit, **une archive unique** `sauvegarde_AAAA-MM-JJ_HHhMM.zip`, qu'un poste
Windows ouvre d'un double-clic :

| Fichier | Contenu |
|---|---|
| `intranet-postgres.sql.gz` | base de l'application |
| `nextcloud-postgres.sql.gz` | base de la messagerie |
| `media.tar.gz` | pièces jointes : documents, courriers, diplômes |
| `nextcloud-data.tar.gz` | fichiers déposés dans la messagerie |
| `configuration/` | `.env`, certificats TLS, `config.php` de Nextcloud |
| `MANIFESTE.txt` | contenu, tailles et commandes de restauration |

L'archive est assemblée dans un dossier de travail caché puis déplacée d'un bloc à sa
place définitive. Une archive visible est donc toujours complète, même si la machine
s'éteint pendant l'opération — la question « celle-ci est-elle utilisable ? » ne se pose
pas.

Le dossier `configuration` mérite une explication : les dumps ne suffisent pas à repartir
d'une machine neuve. Il y faut les mots de passe des bases, que porte le `.env`, et
surtout le `config.php` de Nextcloud — il contient `passwordsalt` et `secret`, sans
lesquels la base Nextcloud restaurée est inexploitable, plus aucun mot de passe ne se
vérifiant. **Ces fichiers contiennent des secrets en clair** : le disque de sauvegarde
doit être gardé comme un classeur du personnel.

### L'onglet « Sauvegarde et restauration »

L'administrateur — et lui seul — dispose dans l'intranet d'un onglet qui liste les
sauvegardes, permet d'en déclencher une, d'en télécharger une, et d'en **restaurer** une.

Restaurer depuis cette page remet en place **la base et les pièces jointes**. La
messagerie n'y est pas incluse : sa restauration suppose d'arrêter les conteneurs
Nextcloud, ce qu'une application ne peut pas faire depuis l'intérieur, et une messagerie
à moitié restaurée est pire qu'une messagerie intacte. Sa procédure reste dans
[docs/RESTAURATION.md](docs/RESTAURATION.md).

Trois garde-fous encadrent le bouton :

1. la capacité est réservée au rôle **Administrateur** — le Directeur Général en est
   écarté comme les autres : restaurer est un acte d'exploitation informatique, pas une
   décision administrative ;
2. il faut recopier le mot `RESTAURER` — un « Êtes-vous sûr ? » se clique sans lire ;
3. **une sauvegarde de l'état actuel est prise avant toute destruction**, et son échec
   annule la restauration. Se tromper d'archive reste rattrapable.

Pendant l'opération, l'application sert une page d'attente qui se rafraîchit seule, puis
rouvre d'elle-même. Cette page ne touche ni à la base ni aux sessions — elles n'existent
pas à cet instant.

**Comment l'application commande le service.** Elle ne sauvegarde ni ne restaure
elle-même : elle n'a pas `pg_dump`, et surtout elle ne peut pas détruire la base à
laquelle elle est connectée. Elle dépose donc un fichier de demande dans un volume
partagé, que le service `backup` exécute et dont il rend compte dans un fichier d'état.
Ce détour vaut mieux que l'alternative — donner au conteneur web l'accès au socket
Docker — qui reviendrait à confier à une application web le pouvoir d'arrêter et de
recréer n'importe quel conteneur de la machine.

### Une sauvegarde manquée est rattrapée

Le planificateur ne compte pas le temps restant jusqu'à l'heure fixée : il **compare la
date réelle** toutes les cinq secondes, et sauvegarde dès qu'un nouveau jour est entamé et
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
BACKUP_DIR=E:/sauvegardes-intranet-dges
```

Si Docker ne parvient pas à créer le dossier, créez-le une fois à la main.

**L'application détecte d'elle-même un disque absent.** Quand Docker ne sait pas résoudre
le disque — débranché, branché après le démarrage de Docker, ou formaté en exFAT que WSL 2
ne monte pas — il crée silencieusement un dossier du même nom dans sa propre machine
virtuelle. Même chemin, espace libre affiché, et pas une sauvegarde derrière.

L'onglet **Sauvegarde et restauration** le reconnaît à deux indices : le témoin
`.disque-sauvegarde`, réécrit à chaque sauvegarde réussie, et la présence d'archives.
Aucun des deux sur un volume trop petit pour un disque de sauvegarde, et la page affiche
une alerte au lieu d'une jauge rassurante — l'espace mesuré ne serait pas celui du disque
attendu. La liste vide est alors expliquée comme telle : les sauvegardes existent, elles
sont sur le disque débranché.

Le planificateur, de son côté, espace ses tentatives de quinze minutes après un échec.
Son tour de boucle est court parce qu'il écoute aussi les demandes de l'application ; sans
ce frein, un disque absent ferait réessayer toutes les cinq secondes et noierait le
journal.

**Vérification manuelle**, après chaque rebranchement :

```powershell
docker run --rm -v "E:/sauvegardes-intranet-dges:/test" alpine df -h /test
```

La taille affichée doit être celle du disque. Le script refuse de démarrer sous 512 Mo
libres (`BACKUP_MIN_FREE_KB`), ce qui bloque le cas courant, mais faites la vérification
après chaque rebranchement. La marche à suivre en cas de dossier fantôme est dans
[docs/DEPLOIEMENT_WINDOWS_LOCAL.md](docs/DEPLOIEMENT_WINDOWS_LOCAL.md).

### Vérifier et déclencher à la main

```powershell
docker compose logs backup                              # journal et prochaine échéance
docker compose exec backup /usr/local/bin/sauvegarde.sh # sauvegarde immédiate
```

### Restaurer

**Le plus simple : l'onglet « Sauvegarde et restauration » de l'intranet.** Choisissez
une sauvegarde, cliquez sur Restaurer, recopiez le mot demandé. L'application se ferme le
temps de l'opération et rouvre seule.

La procédure manuelle, cas par cas — donnée effacée par erreur, base corrompue, pièces
jointes perdues, messagerie perdue, machine morte — est dans
**[docs/RESTAURATION.md](docs/RESTAURATION.md)**. Elle est écrite pour être suivie dans
l'urgence, et ses commandes ont été exécutées telles quelles.

**Essayez la restauration sans rien casser** — restaurez dans une base à côté et comparez
les compteurs, sans toucher à la base vivante :

```powershell
docker compose exec -T backup sh -c 'mkdir -p /sauvegardes/.extraction && unzip -q -o /sauvegardes/sauvegarde_2026-08-04_01h00.zip -d /sauvegardes/.extraction'
docker compose exec -T db psql -U intranet_dges_user -d postgres -c "CREATE DATABASE recuperation;"
docker compose exec -T backup sh -c 'gunzip -c /sauvegardes/.extraction/intranet-postgres.sql.gz | PGPASSWORD="$POSTGRES_PASSWORD" psql -q -h db -U "$POSTGRES_USER" -d recuperation'
docker compose exec -T db psql -U intranet_dges_user -d recuperation -c "select count(*) from courriers_courrier;"
docker compose exec -T db psql -U intranet_dges_user -d postgres -c "DROP DATABASE recuperation;"
docker compose exec -T backup rm -rf /sauvegardes/.extraction
```

L'extraction et le chargement passent par le conteneur `backup`, qui dispose déjà d'`unzip`,
de `psql` et des mots de passe : rien à installer sur Windows.

Cette procédure a été exécutée depuis le disque de sauvegarde, et la restauration
complète a été vérifiée de bout en bout : une donnée créée après la sauvegarde avait bien
disparu après restauration, le reste étant intact.

## Messagerie interne

Nextcloud Talk, servi à côté de l'intranet. Le choix est motivé dans
[docs/ARCHITECTURE_MESSAGERIE_INTERNE.md](docs/ARCHITECTURE_MESSAGERIE_INTERNE.md).

### L'intranet fait autorité sur l'annuaire

Rien ne se crée à la main dans Nextcloud. Un compte agent naît, se modifie et se
désactive dans l'intranet ; la messagerie suit. Sans cette règle les deux annuaires
divergent, et plus personne ne sait lequel dit vrai.

Trois conséquences, qui sont l'essentiel du dispositif :

- **un seul identifiant** — celui de l'intranet, jamais un autre ;
- **un seul mot de passe**. Il est porté à la messagerie aux trois moments où l'intranet
  le connaît en clair : création du compte, réinitialisation par l'administrateur,
  changement par l'agent. Le reste du temps, celui de la messagerie n'est pas touché —
  le remplacer par une valeur aléatoire couperait l'agent de ses conversations ;
- **désactiver un compte ferme la messagerie**, immédiatement. C'est le point qui compte
  le jour où quelqu'un quitte la direction. Supprimer un compte agent désactive son
  compte Nextcloud sans l'effacer : une conversation doit rester lisible et attribuable
  des mois après le départ de celui qui l'a écrite.

### Conversations

Un groupe Nextcloud par service, plus `dges-tous`, et une conversation Talk adossée à
chacun. Elles suivent le groupe : un agent affecté à un service rejoint sa conversation
sans que personne l'y invite, un agent muté la quitte.

Chaque agent voit donc la conversation générale et celle de son service, et pas les
autres.

### Réparer après une panne

La messagerie peut être arrêtée sans que l'intranet cesse de fonctionner : créer un
compte agent réussit même alors, avec un avertissement. Ce qui n'a pas pu passer se
rattrape ensuite :

```powershell
docker compose exec web python manage.py synchroniser_messagerie
docker compose exec web python manage.py synchroniser_messagerie --conversations
```

La commande ne fait que ce qui manque ; deux exécutions de suite donnent le même
résultat.

### Réglages (`.env`)

| Variable | Rôle | Défaut |
|---|---|---|
| `MESSAGERIE_SYNC_ENABLED` | active la synchronisation | `1` |
| `MESSAGERIE_API_URL` | adresse interne de Nextcloud | `http://nextcloud-app` |
| `MESSAGERIE_TIMEOUT` | délai d'attente, en secondes | `10` |

Les identifiants d'administration sont ceux de Nextcloud (`NEXTCLOUD_ADMIN_USER` et
`NEXTCLOUD_ADMIN_PASSWORD`). Attention : ces variables ne servent qu'à **l'installation**
de Nextcloud. Si le mot de passe de l'administrateur a été changé depuis, la
synchronisation échoue avec « identifiants refusés » ; on les réaligne par :

```powershell
docker compose exec -u www-data nextcloud-app php occ user:resetpassword admin_dges
```

Le nom de conteneur `nextcloud-app` doit figurer dans `NEXTCLOUD_TRUSTED_DOMAINS` :
l'appel passe par le réseau Docker interne, et Nextcloud refuse tout hôte absent de
cette liste.

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
