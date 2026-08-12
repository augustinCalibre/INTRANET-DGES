# Deploiement Windows local sur le reseau DGES

> **Etat actuel : la plateforme fonctionne en local uniquement.** Les ports
> n'ecoutent que sur la boucle locale (`127.0.0.1`) et rien n'est joignable
> depuis le reseau, quelles que soient les regles du pare-feu. L'acces se fait
> sur `https://localhost/` et `https://localhost:8443/` depuis la machine
> elle-meme.
>
> Ce guide decrit l'exposition reseau, conservee pour le jour ou elle sera
> reprise. Pour rouvrir l'acces aux equipes, voir « Revenir a l'exposition
> reseau » en fin de document.

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
- utilisateur Windows autorise a lancer Docker Desktop ;
- un **second disque** pour les sauvegardes, distinct de celui qui porte le projet.

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
powershell -ExecutionPolicy Bypass -File .\scripts\windows\mettre-a-jour-production.ps1
```

Ce script fait, dans cet ordre :

- verification que Git et Docker repondent, que `.env` existe, et qu'aucune
  modification locale n'a ete faite sur le serveur ;
- **sauvegarde avant toute modification**, et arret si elle echoue ;
- `git fetch`, `git checkout`, `git pull --ff-only` ;
- controle du `.env`, qui n'est pas versionne et n'a donc pas suivi les
  evolutions du code ;
- reconstruction des images, demarrage, attente des migrations, redemarrage de
  nginx ;
- controles finaux : intranet, messagerie, disque de sauvegarde.

Le detail, les options et la marche a suivre en cas de panne sont dans
[MISE_A_JOUR_PRODUCTION.md](MISE_A_JOUR_PRODUCTION.md).

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
powershell -ExecutionPolicy Bypass -File .\scripts\windows\mettre-a-jour-production.ps1
```

## Ce qu'il ne faut pas faire

- modifier le code directement sur le serveur ;
- creer des fichiers locaux de travail dans le clone serveur ;
- versionner le fichier `.env` ;
- versionner `docker/nginx/certs/` ;
- utiliser un Wi-Fi repeteur comme lien principal du serveur.

## Recommandation reseau importante

Pour l'exposition reseau, branchez le serveur sur le routeur principal et non sur un repeteur. C'est la meilleure facon d'eviter les comportements differents selon la borne Wi-Fi a laquelle le client est connecte.

## Sauvegarde automatique sur le second disque

Le service Docker `backup` sauvegarde chaque nuit sans intervention. Sur le serveur, la
seule chose a faire est de pointer la destination vers le **second disque** : une
sauvegarde posee sur le meme disque que la base ne protege de rien en cas de panne
materielle.

### Mise en place, une seule fois

```powershell
# 1. Creer le dossier (Docker n'y parvient pas toujours sur Windows)
New-Item -ItemType Directory -Force E:\sauvegardes-intranet-dges
```

Puis dans `.env`, en adaptant la lettre du disque :

```env
BACKUP_DIR=E:/sauvegardes-intranet-dges
BACKUP_HOUR=1
BACKUP_RETENTION_DAYS=90
BACKUP_INCLUDE_NEXTCLOUD_FILES=1
```

Avec un disque d'1 To, la retention peut etre large : une sauvegarde complete pese
quelques megaoctets au demarrage du service. Quatre-vingt-dix jours protegent contre une
corruption decouverte tardivement, ce que quatorze jours ne permettent pas.

```powershell
# 2. Appliquer et verifier immediatement
docker compose up -d backup
docker compose exec backup /usr/local/bin/sauvegarde.sh
```

Une archive `sauvegarde_AAAA-MM-JJ_HHhMM.zip` doit apparaitre dans
`E:\sauvegardes-intranet-dges\`. Un double-clic dans l'Explorateur en montre le contenu.

### Le piege du disque que Docker ne voit pas

Quand Docker ne sait pas resoudre un disque de l'hote, il ne refuse pas : il cree
silencieusement un dossier du meme nom **dans sa propre machine virtuelle**. La
sauvegarde s'execute, annonce sa reussite, et rien n'arrive sur le disque. Le cas se
produit dans deux situations :

- le disque n'est pas en **NTFS** — un disque externe livre en exFAT n'est pas monte par
  WSL 2 ; reformatez-le en NTFS ;
- le disque a ete **branche apres le demarrage de Docker** — WSL 2 ne le montera pas de
  lui-meme ; redemarrez Docker Desktop.

Verification, avant de faire confiance a la premiere sauvegarde :

```powershell
docker run --rm -v "E:/sauvegardes-intranet-dges:/test" alpine df -h /test
```

La taille annoncee doit etre celle du disque. Quelques centaines de megaoctets signalent
le dossier fantome. Dans ce cas, supprimez-le avant de recommencer, sinon il continuera de
masquer le vrai point de montage :

```powershell
wsl --shutdown
wsl -d docker-desktop rmdir /mnt/host/e
```

Le script de sauvegarde refuse desormais de demarrer sous 512 Mo libres
(`BACKUP_MIN_FREE_KB`), ce qui bloque le cas le plus courant — mais un disque fantome
plus spacieux passerait au travers. Faites la verification.

### Controles a faire regulierement

```powershell
docker compose logs backup       # journal et heure de la prochaine sauvegarde
```

Plus simplement, l'onglet **Sauvegarde et restauration** de l'intranet, accessible au
compte administrateur, liste les archives, l'espace restant sur le disque et l'historique
des operations.

Une archive presente est toujours complete : elle est assemblee a cote puis deplacee d'un
bloc. Une sauvegarde interrompue ne laisse rien derriere elle, et le journal la signale.

**Testez la restauration au moins une fois**, sur une base d'essai, sans toucher a la base
vivante. La procedure figure dans [RESTAURATION.md](RESTAURATION.md), cas 1. Une
sauvegarde jamais restauree n'est pas une sauvegarde.

### Copie hors machine

Le disque interne protege d'une panne de disque, pas d'un vol, d'un incendie ou d'un
chiffrement par rancongiciel. Prevoyez une copie du dossier de sauvegarde vers un autre
local ou un compte institutionnel.

Attention : ces fichiers contiennent la base complete, donc les donnees personnelles des
agents et des titulaires de diplomes. Un compte cloud personnel n'est pas un support
approprie.

## Demarrage quotidien

Pour cette phase Windows temporaire :

- laissez le PC serveur allume ;
- laissez Docker Desktop demarre ;
- si le PC redemarre, reconnectez-vous une fois pour que Docker Desktop reparte, puis relancez le script de demarrage si besoin.

### Le point sensible : Docker Desktop exige une session ouverte

C'est la principale faiblesse de Windows pour ce role, et il faut la traiter
explicitement. Docker Desktop ne tourne pas comme un service systeme : il s'execute dans
la session de l'utilisateur. **Si personne n'est connecte, la pile ne demarre pas** — et
la sauvegarde de la nuit n'a pas lieu non plus.

Trois reglages a faire sur le serveur :

1. **Docker Desktop au demarrage** : *Settings > General > Start Docker Desktop when you
   sign in*, et *Settings > General > Open Docker Dashboard at startup* peut rester
   decoche.
2. **Ouverture de session automatique** pour un compte dedie au serveur, afin que la
   session existe apres un redemarrage ou une coupure de courant
   (`netplwiz`, decocher « Les utilisateurs doivent entrer un nom d'utilisateur… »).
3. **Verrouiller l'ecran, ne jamais fermer la session** : `Win + L` verrouille en
   conservant la session ; « Se deconnecter » arreterait Docker et toute la pile.

Ajoutez une verification apres chaque coupure de courant :

```powershell
docker compose ps          # les 8 services doivent etre Up
docker compose logs backup # la sauvegarde doit annoncer sa prochaine echeance
```

Pour une vraie disponibilite quotidienne automatique, Ubuntu Server reste plus propre que
Windows : Docker y demarre comme un service, sans session ouverte, et la sauvegarde tourne
meme serveur non supervise.

## Resume tres court pour aujourd'hui

1. branchez le PC serveur en RJ45 sur le routeur principal ;
2. donnez-lui une IP fixe ;
3. copiez le projet complet ou clonez-le depuis GitHub ;
4. recopiez `.env` et `docker/nginx/certs/` ;
5. ouvrez les ports avec `open-firewall-ports.ps1` ;
6. lancez `start-local-stack.ps1 -Build` ;
7. testez `https://IP_DU_SERVEUR/` depuis un autre poste ;
8. pointez `BACKUP_DIR` vers le second disque, puis lancez une sauvegarde de controle ;
9. reglez le demarrage automatique de Docker Desktop et l'ouverture de session ;
10. pour chaque mise a jour : `git push` ici, puis `mettre-a-jour-production.ps1` sur le serveur.

La procedure complete, avec les pannes courantes et la marche a suivre, est dans
[MISE_A_JOUR_PRODUCTION.md](MISE_A_JOUR_PRODUCTION.md).

## Revenir a l'exposition reseau

La plateforme tourne aujourd'hui en local uniquement. Trois changements la
rouvrent aux equipes, et il faut les trois : chacun pris seul laisse l'acces
ferme.

**1. Publier les ports au-dela de la boucle locale.** Dans `docker-compose.yml`,
service `nginx`, retirer le prefixe `127.0.0.1:` :

```yaml
    ports:
      - "80:80"
      - "443:443"
      - "8443:8443"
```

**2. Declarer l'adresse du serveur.** Dans `.env`, ajouter l'adresse fixe a
`ALLOWED_HOSTS` et a `NEXTCLOUD_TRUSTED_DOMAINS`, et retablir les URL :

```env
ALLOWED_HOSTS=localhost,127.0.0.1,192.168.100.X,intranet-dges.local,messagerie.dges.local
INTRANET_HOSTNAME=intranet-dges.local
INTRANET_URL=https://intranet-dges.local
INTRANET_FALLBACK_URL=https://192.168.100.X
MESSAGING_URL=https://messagerie.dges.local:8443
MESSAGING_FALLBACK_URL=https://192.168.100.X:8443
NEXTCLOUD_TRUSTED_DOMAINS=localhost 127.0.0.1 messagerie.dges.local intranet-dges.local 192.168.100.X
NEXTCLOUD_OVERWRITE_CLI_URL=https://messagerie.dges.local:8443
```

**3. Fixer l'adresse.** Une adresse obtenue par DHCP change, et chaque
changement casse l'acces de tout le monde en silence : le nom ne resout plus,
et l'application refuse une adresse qu'elle ne connait pas. Reservez l'adresse
sur le routeur a partir de l'adresse MAC, ou configurez-la en statique sur la
carte reseau. Preferez le RJ45 au Wi-Fi.

Puis appliquer, en n'oubliant pas de relancer nginx apres avoir recree `web` —
il garde en memoire l'ancienne adresse du conteneur et repondrait 502 :

```powershell
docker compose up -d
docker compose restart nginx
```

### Pieges rencontres, a ne pas redecouvrir

- **Apres un redemarrage de Docker Desktop**, le relais de ports peut rester
  sur l'ancien demon : la connexion TCP aboutit mais rien ne repond.
  `docker compose restart nginx` retablit la situation.
- **Apres avoir recree le conteneur `web`**, nginx pointe encore sur son
  ancienne adresse et renvoie 502. Meme remede.
- **`NEXTCLOUD_TRUSTED_DOMAINS` est reapplique a chaque demarrage** du
  conteneur : une valeur ajoutee a la main avec `occ` se retrouve en double.
  Modifier `.env`, pas la configuration en place.
