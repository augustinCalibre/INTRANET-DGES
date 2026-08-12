# Mettre à jour l'intranet DGES en production

Deux scripts couvrent l'essentiel. Le reste de ce document explique ce qu'ils
font, et quoi faire quand ils s'arrêtent.

```powershell
cd C:\intranet-dges                                    # dossier du projet
.\scripts\windows\mettre-a-jour-production.ps1         # récupérer et déployer
.\scripts\windows\creer-comptes-dges.ps1               # créer les comptes
```

Le second n'est à lancer **qu'une fois**, à la mise en service. Le premier se
relance à chaque livraison.

---

## Avant la première mise à jour

Le dépôt ne contient ni le fichier `.env` ni les certificats : ce sont les
seuls éléments à installer à la main.

```powershell
git clone https://github.com/augustinCalibre/INTRANET-DGES.git C:\intranet-dges
cd C:\intranet-dges
```

Recopiez depuis le poste de développement, ou depuis une archive de sauvegarde
(dossier `configuration/`) :

- `.env`
- `docker\nginx\certs\`

Puis démarrez une première fois :

```powershell
docker compose up -d
```

---

## Mettre à jour : `mettre-a-jour-production.ps1`

Le script enchaîne, dans cet ordre :

1. **vérifications** — Git, Docker, `.env` présent, aucune modification locale
   non validée. Le serveur ne doit jamais être modifié directement : ce qui y
   est corrigé à la main est perdu à la mise à jour suivante ;
2. **sauvegarde** avant toute modification. Si elle échoue, le script
   s'arrête — on ne modifie pas une installation qu'on ne saurait pas
   restaurer ;
3. `git pull` sur la branche demandée ;
4. **contrôle du `.env`**, qui n'est pas versionné et n'a donc pas suivi les
   évolutions du code ;
5. **reconstruction** des images `web` et `backup` ;
6. **démarrage**, puis attente des migrations, puis redémarrage de nginx ;
7. **contrôles** : intranet, messagerie, disque de sauvegarde, synchronisation.

Il affiche à la fin ce qui va bien et ce qui reste à traiter.

### Options

```powershell
.\scripts\windows\mettre-a-jour-production.ps1 -Branche main
.\scripts\windows\mettre-a-jour-production.ps1 -SansSauvegarde
```

`-SansSauvegarde` n'est à utiliser que si une sauvegarde vient d'être prise à
la main.

### Pourquoi ces deux redémarrages

Ce sont deux pièges qui ont coûté des heures, et que le script traite seul :

- **nginx garde en mémoire l'adresse du conteneur `web`.** Recréé, celui-ci
  change d'adresse et nginx répond `502` jusqu'à ce qu'on le relance ;
- **après un redémarrage de Docker Desktop**, le relais de ports peut rester
  sur l'ancien démon : la connexion aboutit, mais rien ne répond. Même remède.

---

## Créer les comptes : `creer-comptes-dges.ps1`

Le script reprend l'état du personnel décrit dans
[accounts/annuaire_dges.py](../accounts/annuaire_dges.py) : huit services,
quatorze agents. Pour chacun, un compte intranet **et** un accès à la
messagerie sont créés ensemble, avec le même identifiant et le même mot de
passe.

Il demande confirmation, prend une sauvegarde, puis affiche le tableau des
identifiants à distribuer.

```powershell
.\scripts\windows\creer-comptes-dges.ps1
.\scripts\windows\creer-comptes-dges.ps1 -DesactiverComptesDemo
.\scripts\windows\creer-comptes-dges.ps1 -MotDePasse "AutreSecret2026!"
```

**Il peut être relancé sans crainte** : il ne crée que ce qui manque, ne
supprime rien, et ne rétablit pas le mot de passe d'un compte existant — un
agent qui a choisi le sien ne doit pas le voir revenir au mot de passe commun.

`-DesactiverComptesDemo` désactive les comptes absents de l'annuaire, sans les
supprimer : leurs courriers, tâches et documents gardent leur auteur.

`-ReinitialiserMotsDePasse` remet le mot de passe commun sur tous les comptes.
À n'utiliser qu'avant la première distribution des accès.

### Le mot de passe initial

Dix caractères au minimum : c'est ce qu'exige la politique de mots de passe de
Nextcloud, et le même secret doit valoir pour l'intranet et la messagerie. La
valeur par défaut est `DGES-2026!`.

Il ne survit pas à la première connexion : l'application impose son changement,
et le nouveau mot de passe est porté à la messagerie. C'est la seule façon
qu'il ne finisse pas noté sur un papier au dos d'un clavier.

---

## Modifier l'annuaire plus tard

Pour un agent qui arrive, qui part ou qui change de service, **passez par
l'intranet** — panneau *Accès et comptes*. La messagerie suit automatiquement :
compte créé, mot de passe porté, accès fermé à la désactivation.

`annuaire_dges.py` et le script ne servent qu'à la mise en service initiale, ou
à recréer l'ensemble sur une machine neuve.

---

## Quand quelque chose ne va pas

### « Des modifications locales non validées sont présentes »

Quelqu'un a modifié un fichier directement sur le serveur. Regardez quoi, puis
annulez :

```powershell
git status
git diff
git checkout -- .          # annule tout, à ne faire qu'après avoir regardé
```

### L'intranet répond 502

nginx pointe sur une ancienne adresse du conteneur web :

```powershell
docker compose restart nginx
```

### « Identifiants d'administration de la messagerie refusés »

`NEXTCLOUD_ADMIN_PASSWORD` dans `.env` ne sert qu'à **l'installation** de
Nextcloud. Si le mot de passe a été changé depuis, la synchronisation échoue.
On les réaligne :

```powershell
docker compose exec -u www-data nextcloud-app php occ user:resetpassword admin_dges
```

en saisissant la valeur exacte de `NEXTCLOUD_ADMIN_PASSWORD`. Puis :

```powershell
docker compose exec web python manage.py synchroniser_messagerie
```

### Le disque de sauvegarde est signalé injoignable

Un disque branché après le démarrage de Docker n'est pas monté, et Docker écrit
alors dans sa propre machine virtuelle. La marche à suivre est dans
[DEPLOIEMENT_WINDOWS_LOCAL.md](DEPLOIEMENT_WINDOWS_LOCAL.md), section « Le piège
du disque que Docker ne voit pas ».

### Revenir en arrière

La sauvegarde prise au début de la mise à jour permet de restaurer l'état
précédent. La procédure est dans [RESTAURATION.md](RESTAURATION.md), ou depuis
l'onglet *Sauvegarde et restauration* de l'intranet.

Pour revenir à la version précédente du code :

```powershell
git log --oneline -5
git checkout <empreinte>
docker compose build web backup
docker compose up -d
docker compose restart nginx
```

Attention : une version antérieure du code peut ne pas savoir lire une base
déjà migrée. Restaurez alors aussi la base, depuis la sauvegarde prise avant la
mise à jour.

---

## Ce qu'il ne faut pas faire

- modifier le code directement sur le serveur ;
- créer des comptes à la main dans Nextcloud — l'intranet fait autorité, et
  deux annuaires qui divergent ne se rattrapent pas ;
- versionner `.env` ou `docker\nginx\certs\` ;
- lancer une mise à jour sans sauvegarde en état de marche.
