# Restaurer l'intranet DGES après une panne

Ce document se lit dans l'urgence. Chaque cas est indépendant : identifiez le vôtre,
appliquez la section correspondante, ignorez le reste.

Toutes les commandes se lancent depuis le dossier du projet, dans PowerShell, avec
Docker Desktop démarré. Elles passent volontairement par les conteneurs : rien à
installer sur Windows.

---

## D'abord : essayez l'onglet de l'intranet

Pour les deux cas les plus fréquents — **base corrompue** et **pièces jointes
perdues** — il n'y a rien à taper. Connectez-vous à l'intranet avec le compte
administrateur, ouvrez **Sauvegarde et restauration**, choisissez une sauvegarde dans
la liste, cliquez sur **Restaurer**.

L'application se met en maintenance, restaure la base et les pièces jointes, puis
rouvre d'elle-même. Une sauvegarde de l'état actuel est prise automatiquement avant de
commencer : si vous vous êtes trompé d'archive, elle est là.

Ce document reste nécessaire dans trois situations :

- **la messagerie** est à restaurer — l'onglet ne la touche pas (cas 4) ;
- **l'intranet ne démarre plus du tout**, donc l'onglet est inaccessible (cas 2) ;
- **la machine est morte** et tout est à reconstruire (cas 5).

---

## Avant de commencer : trois réflexes

**1. Sauvegardez l'état actuel, même dégradé.** Une restauration écrase. Si vous vous
trompez de sauvegarde, l'état d'aujourd'hui aura disparu à son tour.

```powershell
docker compose exec backup /usr/local/bin/sauvegarde.sh
```

Si la base est trop abîmée pour être sauvegardée, passez outre — mais notez-le.

**2. Choisissez la sauvegarde.** Ce sont des fichiers ZIP dans
`E:\sauvegardes-intranet-dges`, un par jour, nommés `sauvegarde_AAAA-MM-JJ_HHhMM.zip`.

```powershell
Get-ChildItem E:\sauvegardes-intranet-dges -Filter *.zip | Sort-Object Name -Descending | Select-Object -First 10 Name, @{N='Taille';E={"$([math]::Round($_.Length/1MB,1)) Mo"}}, LastWriteTime
```

Prenez **la plus récente antérieure à l'incident**. Un double-clic dans l'Explorateur
Windows en montre le contenu, et le `MANIFESTE.txt` qu'elle contient en rappelle la date
exacte.

Une archive présente est toujours complète : le script l'assemble à côté puis la déplace
d'un bloc. La question « celle-ci est-elle utilisable ? » ne se pose pas.

**3. Notez le nom retenu.** Il revient dans toutes les commandes. Dans ce document il
s'écrit `sauvegarde_2026-08-04_01h00.zip` : remplacez-le partout.

---

## Étape commune : ouvrir l'archive

Les cas 1 à 4 travaillent sur le contenu de l'archive. On l'extrait une fois, dans un
dossier de travail sur le disque de sauvegarde.

```powershell
docker compose exec -T backup sh -c 'rm -rf /sauvegardes/.extraction && mkdir -p /sauvegardes/.extraction && unzip -q /sauvegardes/sauvegarde_2026-08-04_01h00.zip -d /sauvegardes/.extraction && ls -R /sauvegardes/.extraction'
```

Vous devez voir `intranet-postgres.sql.gz`, `media.tar.gz`, et le dossier
`configuration`. À la fin de l'opération, effacez ce dossier de travail :

```powershell
docker compose exec -T backup rm -rf /sauvegardes/.extraction
```

---

## Cas 1 — Une donnée a été effacée par erreur

Ce n'est pas une panne, et il ne faut surtout pas restaurer la base entière : vous
perdriez tout le travail fait depuis la sauvegarde. On restaure **à côté**, on lit, on
recopie à la main.

```powershell
docker compose exec -T db psql -U intranet_dges_user -d postgres -c "CREATE DATABASE recuperation;"
docker compose exec -T backup sh -c 'gunzip -c /sauvegardes/.extraction/intranet-postgres.sql.gz | PGPASSWORD="$POSTGRES_PASSWORD" psql -q -h db -U "$POSTGRES_USER" -d recuperation'
```

Consultez ce dont vous avez besoin, par exemple un courrier supprimé :

```powershell
docker compose exec -T db psql -U intranet_dges_user -d recuperation -c "select reference, objet, expediteur from courriers_courrier order by created_at desc limit 20;"
```

Ressaisissez l'information dans l'application, puis effacez la base de récupération :

```powershell
docker compose exec -T db psql -U intranet_dges_user -d postgres -c "DROP DATABASE recuperation;"
```

---

## Cas 2 — La base de l'application est corrompue

Symptômes : l'application affiche une erreur serveur sur toutes les pages, ou
`docker compose logs web` montre des erreurs PostgreSQL répétées.

**Si l'intranet répond encore, faites-le depuis l'onglet « Sauvegarde et
restauration ».** Ce qui suit sert quand il ne répond plus.

**Tout ce qui a été saisi depuis la sauvegarde sera perdu.** Vérifiez d'abord qu'il
s'agit bien de la base et non d'autre chose : `docker compose logs db --tail 50`.

```powershell
# 1. Fermer l'application aux utilisateurs
docker compose stop web

# 2. Remplacer la base par une base vide
docker compose exec -T db psql -U intranet_dges_user -d postgres -c "DROP DATABASE intranet_dges;"
docker compose exec -T db psql -U intranet_dges_user -d postgres -c "CREATE DATABASE intranet_dges;"

# 3. Recharger la sauvegarde
docker compose exec -T backup sh -c 'gunzip -c /sauvegardes/.extraction/intranet-postgres.sql.gz | PGPASSWORD="$POSTGRES_PASSWORD" psql -q -h db -U "$POSTGRES_USER" -d intranet_dges'

# 4. Rouvrir
docker compose start web
```

Si l'étape 2 refuse de supprimer la base parce qu'elle est utilisée, coupez aussi les
connexions restantes :

```powershell
docker compose exec -T db psql -U intranet_dges_user -d postgres -c "select pg_terminate_backend(pid) from pg_stat_activity where datname='intranet_dges';"
```

Passez ensuite aux vérifications en fin de document.

---

## Cas 3 — Les pièces jointes ont disparu

Les courriers, diplômes et documents s'affichent mais leurs fichiers ne s'ouvrent plus.

Là encore, l'onglet de l'intranet le fait seul. Manuellement :

```powershell
docker compose stop web
docker run --rm -v v1_media_data:/media -v "E:\sauvegardes-intranet-dges\.extraction:/sauvegarde:ro" alpine sh -c "rm -rf /media/* && tar -xzf /sauvegarde/media.tar.gz -C /media"
docker compose start web
```

---

## Cas 4 — La messagerie est perdue

Nextcloud a trois éléments à restaurer, et **les trois ensemble** : sa base, ses
fichiers, et sa configuration. Restaurer la base sans le `config.php` d'origine donne
une messagerie où plus personne ne peut se connecter — les mots de passe sont vérifiés
à l'aide du `passwordsalt` qu'il contient.

C'est la raison pour laquelle l'onglet de l'intranet ne s'en charge pas : il faudrait
arrêter les conteneurs Nextcloud, ce qu'une application ne peut pas faire depuis
l'intérieur, et une messagerie à moitié restaurée est pire qu'une messagerie intacte.

```powershell
# 1. Arrêter la messagerie
docker compose stop nextcloud-app nextcloud-cron

# 2. La configuration (indispensable, à faire en premier)
docker run --rm -v v1_nextcloud_config:/config -v "E:\sauvegardes-intranet-dges\.extraction\configuration:/sauvegarde:ro" alpine sh -c "tar -xzf /sauvegarde/nextcloud-config.tar.gz -C /config"

# 3. La base
docker compose exec -T nextcloud-db psql -U nextcloud_dges_user -d postgres -c "DROP DATABASE nextcloud_dges;"
docker compose exec -T nextcloud-db psql -U nextcloud_dges_user -d postgres -c "CREATE DATABASE nextcloud_dges;"
docker compose exec -T backup sh -c 'gunzip -c /sauvegardes/.extraction/nextcloud-postgres.sql.gz | PGPASSWORD="$NEXTCLOUD_POSTGRES_PASSWORD" psql -q -h nextcloud-db -U "$NEXTCLOUD_POSTGRES_USER" -d nextcloud_dges'

# 4. Les fichiers
docker run --rm -v v1_nextcloud_data:/data -v "E:\sauvegardes-intranet-dges\.extraction:/sauvegarde:ro" alpine sh -c "rm -rf /data/* && tar -xzf /sauvegarde/nextcloud-data.tar.gz -C /data"

# 5. Redémarrer et sortir du mode maintenance si besoin
docker compose start nextcloud-app nextcloud-cron
docker compose exec -u www-data nextcloud-app php occ maintenance:mode --off
```

---

## Cas 5 — La machine est morte

Disque défaillant, vol, incendie. Vous repartez d'une machine neuve, avec le disque de
sauvegarde en main.

L'archive contient tout ce qui ne se retrouve pas ailleurs. Le reste — le code, les
images Docker — se retélécharge.

```powershell
# 1. Installer Docker Desktop et Git, puis récupérer le projet
git clone https://github.com/augustinCalibre/INTRANET-DGES.git
cd INTRANET-DGES

# 2. Ouvrir l'archive. Docker n'étant pas encore configuré, on passe par Windows.
Expand-Archive -Path "E:\sauvegardes-intranet-dges\sauvegarde_2026-08-04_01h00.zip" -DestinationPath "E:\sauvegardes-intranet-dges\.extraction" -Force

# 3. Remettre la configuration : c'est elle qui porte les mots de passe des bases
Copy-Item "E:\sauvegardes-intranet-dges\.extraction\configuration\env.txt" .env
New-Item -ItemType Directory -Force docker\nginx\certs | Out-Null
```

Ouvrez `.env` et adaptez ce qui dépend de la machine : `ALLOWED_HOSTS` et les adresses
IP si elles ont changé. **Ne modifiez ni `POSTGRES_PASSWORD`, ni
`NEXTCLOUD_POSTGRES_PASSWORD`, ni `SECRET_KEY`** : les bases que vous allez restaurer
les attendent tels quels.

```powershell
# 4. Démarrer la pile : elle crée des bases vides
docker compose up -d

# 5. Les certificats, une fois Docker disponible
docker run --rm -v "${PWD}\docker\nginx\certs:/certs" -v "E:\sauvegardes-intranet-dges\.extraction\configuration:/sauvegarde:ro" alpine sh -c "tar -xzf /sauvegarde/certificats.tar.gz -C /certs"
docker compose restart nginx
```

Attendez que `docker compose ps` montre `db` et `nextcloud-db` en `healthy`, puis
appliquez le **cas 2**, le **cas 3** et le **cas 4** dans cet ordre.

Terminez par la configuration réseau du poste, décrite dans
[DEPLOIEMENT_WINDOWS_LOCAL.md](DEPLOIEMENT_WINDOWS_LOCAL.md) : ouverture des ports du
pare-feu, adresse IP fixe, démarrage automatique de Docker Desktop avec ouverture de
session automatique.

---

## Vérifier qu'une restauration a réussi

Ne vous fiez pas à l'absence de message d'erreur. Comptez.

```powershell
docker compose exec -T db psql -U intranet_dges_user -d intranet_dges -c "select 'courriers' as objet, count(*) from courriers_courrier union all select 'diplomes', count(*) from diplomas_diplome union all select 'taches', count(*) from tasks_task union all select 'comptes', count(*) from auth_user;"
```

Comparez ces nombres à ce que vous savez de l'activité du service. Puis, dans
l'application :

- connectez-vous avec un compte non administrateur ;
- ouvrez un courrier et **téléchargez sa pièce jointe** — c'est le seul contrôle qui
  prouve que base et fichiers sont cohérents entre eux ;
- vérifiez le tableau de bord du DG.

Enfin, relancez une sauvegarde pour repartir sur une base saine, et effacez le dossier
de travail :

```powershell
docker compose exec backup /usr/local/bin/sauvegarde.sh
docker compose exec -T backup rm -rf /sauvegardes/.extraction
```

---

## Ce qu'il faut savoir avant d'en avoir besoin

**Les archives contiennent des mots de passe en clair**, dans leur dossier
`configuration`. Le disque de sauvegarde doit rester dans un local fermé, au même titre
qu'un classeur de dossiers du personnel. Il en va de même d'une archive téléchargée
depuis l'intranet.

**Un disque de sauvegarde branché sur la même machine ne protège pas de tout.** Il
couvre la panne de disque, pas le vol ni l'incendie. Emportez périodiquement une copie
d'une archive hors du bâtiment — le bouton **Télécharger** de l'onglet est fait pour
cela.

**Essayez cette procédure une fois, à froid.** Le cas 1 se teste sans aucun risque : il
ne touche pas à la base vivante. Faites-le une fois par trimestre. Une restauration
jamais essayée n'est pas une restauration.
