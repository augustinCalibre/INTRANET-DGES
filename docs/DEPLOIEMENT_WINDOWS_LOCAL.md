# Deploiement Windows local sur le reseau DGES

Ce guide couvre le besoin le plus urgent : exposer rapidement l'intranet sur le reseau local a partir d'un PC Windows relie au routeur en RJ45, puis mettre a jour le serveur depuis GitHub.

## Strategie recommandee

Pour aujourd'hui, la strategie la plus simple et la plus fiable est la suivante :

1. le PC serveur Windows reste branche en RJ45 sur le routeur principal ;
2. vous lui donnez une IP stable ;
3. vous deployez la pile Docker dessus ;
4. les agents accedent d'abord a l'intranet via l'IP du serveur ;
5. vous continuez a developper sur votre poste actuel ;
6. vous poussez sur GitHub ;
7. le serveur recupere les mises a jour par `git pull` puis redemarre la pile Docker.

## Pourquoi cette approche

- elle evite de copier tout le projet manuellement a chaque modification ;
- elle garde la base PostgreSQL, les fichiers medias et les volumes Docker sur le serveur ;
- elle vous permet de corriger ici, pousser sur GitHub, puis actualiser rapidement le serveur ;
- elle est suffisante pour une phase d'exposition reseau locale avant la mise en production Ubuntu.

## Point important sur le nom de domaine local

Pour demarrer vite, utilisez d'abord l'IP du serveur :

- `https://IP_DU_SERVEUR/`

Le nom `intranet-dges.local` viendra apres, quand vous aurez :

- soit ajoute une entree DNS locale sur le routeur ou un serveur DNS ;
- soit ajoute une entree `hosts` sur chaque poste client.

Sans cela, le nom `.local` ne sera pas resolu partout.

## Prerequis sur le PC serveur Windows

- Windows 10 ou 11 ;
- Docker Desktop installe et demarre ;
- Git installe ;
- acces Internet temporaire pour cloner le depot et recuperer les images Docker ;
- connexion RJ45 vers le routeur principal ;
- utilisateur Windows autorise a lancer Docker Desktop.

## Etape 1 - Fixer l'IP du serveur

Le mieux est une reservation DHCP sur le routeur principal.

Exemple :

- serveur intranet : `192.168.100.10`

Ensuite adaptez le fichier `.env` du serveur :

- `ALLOWED_HOSTS=localhost,127.0.0.1,192.168.100.10,intranet-dges.local,messagerie.dges.local`
- `INTRANET_FALLBACK_URL=https://192.168.100.10`
- `MESSAGING_FALLBACK_URL=https://192.168.100.10:8443`
- `NEXTCLOUD_TRUSTED_DOMAINS=messagerie.dges.local intranet-dges.local 192.168.100.10`

## Etape 2 - Initialiser le serveur

Deux options sont possibles.

### Option A - La plus rapide aujourd'hui

Copiez tout le dossier actuel du projet vers le PC serveur, avec :

- le fichier `.env` ;
- le dossier `docker/nginx/certs/`.

Cette option est la plus rapide car `.env` et les certificats ne sont pas versionnes dans Git.

### Option B - Plus propre des le debut

Clonez le depot GitHub sur le serveur, puis recopiez a la main :

- `.env`
- `docker/nginx/certs/`

Exemple :

```powershell
git clone https://github.com/VOTRE_ORGANISATION/intranet-dges.git C:\intranet-dges
cd C:\intranet-dges
```

## Etape 3 - Ouvrir les ports Windows

Dans PowerShell lance en administrateur :

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\open-firewall-ports.ps1
```

Ports ouverts :

- `80`
- `443`
- `8443`

## Etape 4 - Demarrer la pile Docker

Depuis le dossier du projet sur le serveur :

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\start-local-stack.ps1 -Build
```

Puis creez le compte administrateur Django si necessaire :

```powershell
docker compose exec web python manage.py createsuperuser
```

## Etape 5 - Verifier l'acces reseau

Depuis le PC serveur :

- `https://127.0.0.1/`
- `https://IP_DU_SERVEUR/`

Depuis un autre poste du reseau :

- `https://IP_DU_SERVEUR/`

Remarque :

- si le navigateur affiche un avertissement de certificat, c'est normal avec un certificat local auto-signe ;
- pour aujourd'hui, cela n'empeche pas la demonstration interne.

## Workflow de mise a jour depuis GitHub

Une fois le serveur en place :

1. vous developpez sur votre poste de travail ;
2. vous committez ;
3. vous poussez sur GitHub ;
4. sur le serveur, vous lancez la mise a jour.

Commande serveur :

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\update-from-github.ps1 -Branch main -Build
```

Ce script fait :

- verification qu'il n'y a pas de modifications locales non committees ;
- `git fetch` ;
- `git checkout main` ;
- `git pull --ff-only` ;
- `docker compose up -d --remove-orphans --build`.

## Routine simple de travail

Sur le poste de developpement :

```powershell
git add .
git commit -m "Votre message"
git push origin main
```

Sur le serveur :

```powershell
cd C:\intranet-dges
powershell -ExecutionPolicy Bypass -File .\scripts\windows\update-from-github.ps1 -Branch main -Build
```

## Ce qu'il ne faut pas faire

- modifier le code directement sur le serveur ;
- creer des fichiers locaux de travail dans le clone serveur ;
- versionner le fichier `.env` ;
- versionner `docker/nginx/certs/` ;
- utiliser un Wi-Fi repeteur comme lien principal du serveur.

## Recommandation reseau importante

Pour l'exposition reseau, branchez le serveur sur le routeur principal et non sur un repeteur. C'est la meilleure facon d'eviter les comportements differents selon la borne Wi-Fi a laquelle le client est connecte.

## Demarrage quotidien

Pour cette phase Windows temporaire :

- laissez le PC serveur allume ;
- laissez Docker Desktop demarre ;
- si le PC redemarre, reconnectez-vous une fois pour que Docker Desktop reparte, puis relancez le script de demarrage si besoin.

Pour une vraie disponibilite quotidienne automatique, Ubuntu Server sera plus propre que Windows.

## Resume tres court pour aujourd'hui

1. branchez le PC serveur en RJ45 sur le routeur principal ;
2. donnez-lui une IP fixe ;
3. copiez le projet complet ou clonez-le depuis GitHub ;
4. recopiez `.env` et `docker/nginx/certs/` ;
5. ouvrez les ports avec `open-firewall-ports.ps1` ;
6. lancez `start-local-stack.ps1 -Build` ;
7. testez `https://IP_DU_SERVEUR/` depuis un autre poste ;
8. pour chaque mise a jour : `git push` ici, puis `update-from-github.ps1 -Build` sur le serveur.
