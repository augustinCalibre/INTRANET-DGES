# Audit de l'existant — Intranet DGES V1

Date de l'audit : 29 juillet 2026
Périmètre : code applicatif, configuration, sécurité, infrastructure de déploiement, exploitation.
Méthode : lecture intégrale du code source (7 applications Django, ~4 100 lignes Python, 16 gabarits), de la configuration Docker/Nginx et des documents d'exploitation. `manage.py check` et `check --deploy` exécutés. La suite de tests n'a pas été lancée.

> **Suivi au 29 juillet 2026.** Deux points de ce rapport ont été traités depuis :
> **B4 (fuseau horaire)** — `DJANGO_TIME_ZONE=Africa/Kinshasa` est désormais défini dans
> `.env` et `.env.example` ; **m1 bis** — `MESSAGE_TAGS` mappe le niveau `error` de Django
> sur la classe `danger` de Bootstrap, les messages d'erreur s'affichent donc bien en rouge.
> Le module Lots de diplômes ajouté ensuite est livré avec pagination et tests
> (49 tests au total, tous passants). Les points **B1**, **B2** et **B3** restent ouverts et
> demeurent prioritaires.

---

## 1. Synthèse

L'application est **fonctionnelle, cohérente et bien structurée** pour une V1. Le socle technique est sain : Django 5.2.13, séparation nette `models / forms / selectors / views`, permissions centralisées, aucune dépendance Internet à l'exécution (Bootstrap et Flatpickr servis localement — choix pertinent pour un intranet).

Les problèmes identifiés ne sont pas des problèmes de conception mais des **problèmes d'industrialisation** : le projet a été développé comme une maquette avancée et n'a pas franchi les étapes qui séparent une maquette d'un service administratif exploité quotidiennement.

Trois constats dominent :

1. **Aucun contrôle de version.** Le projet n'est pas un dépôt Git. Aucun historique, aucun retour arrière possible, aucune trace de qui a modifié quoi.
2. **Configuration de production incomplète.** Les mots de passe de bases de données sont restés aux valeurs d'exemple ; le fuseau horaire est UTC alors que toute l'application raisonne en jour et heure locaux.
3. **Aucune pagination et aucune tâche planifiée.** Les listes se dégraderont mécaniquement avec le volume, et les rappels de réunion ne partent que si un agent navigue au bon moment.

| Domaine | Appréciation |
|---|---|
| Architecture applicative | Bonne |
| Modèle de données | Bon |
| Contrôle d'accès (code) | Bon, avec une faille de conception sur les réunions |
| Configuration de production | Insuffisante |
| Passage à l'échelle | Insuffisant |
| Exploitation / sauvegarde | Partielle |
| Tests | Insuffisants |
| Gestion du code source | Absente |

---

## 2. Inventaire de l'existant

### 2.1 Applications Django

| Application | Rôle | Volume |
|---|---|---|
| `core` | Accueil, journal d'activité, notifications, permissions, utilitaires, données de démonstration | ~800 lignes |
| `accounts` | Services, profils, rôles, groupes, comptes agents, authentification | ~350 lignes |
| `dashboard` | Tableau de bord et indicateurs | ~115 lignes |
| `visitors` | Registre des visiteurs, entrée/sortie | ~240 lignes |
| `tasks` | Tâches, historique, vue liste et kanban | ~390 lignes |
| `documents` | Documents et courriers, upload, archivage, téléchargement contrôlé | ~380 lignes |
| `meetings` | Réunions, convocations, notifications, calendrier, rappels | ~720 lignes |

### 2.2 Modèle de données

10 modèles, 10 migrations, aucune migration en attente (`manage.py check` : aucun problème).

`Service`, `UserProfile` — `Visitor` — `Task`, `TaskHistory` — `Document` — `Meeting` — `ActivityLog`, `Notification`.

Le modèle est simple et lisible : nommage français cohérent, `verbose_name` renseignés partout, `TextChoices` pour tous les statuts, `ordering` par défaut sur chaque `Meta`. Les `on_delete` sont réfléchis (`SET_NULL` pour les auteurs, `CASCADE` pour les historiques).

### 2.3 Infrastructure

Pile `docker-compose` à 7 services :

- `web` — Django/Gunicorn (3 workers)
- `db` — PostgreSQL 16
- `nginx` — reverse proxy, TLS, ports 80/443/8443
- `nextcloud-app`, `nextcloud-db`, `nextcloud-redis`, `nextcloud-cron` — messagerie Nextcloud Talk

Déploiement Ubuntu documenté (`docs/EXPLOITATION.md`), unité systemd fournie, script de sauvegarde fourni, certificats TLS auto-signés générés pour `.local`.

### 2.4 Rôles et droits

5 rôles : `directeur_general`, `secretariat`, `administrateur`, `responsable_service`, `agent_simple`.
Chaque rôle correspond à un groupe Django dont les permissions sont recréées automatiquement (`post_migrate` + `post_save` sur `UserProfile`). Un groupe supplémentaire « Service Courrier » est attribué selon le drapeau `Service.est_service_courrier`. `is_staff` est dérivé du rôle, jamais saisi à la main. C'est un bon mécanisme.

---

## 3. Points forts à préserver

Ces éléments sont bien faits et ne doivent pas être remis en cause lors des évolutions.

1. **Filtrage de visibilité systématique.** Chaque application expose un `get_visible_*(user)` dans `selectors.py`, et toutes les vues de détail/édition font `get_object_or_404(get_visible_tasks(request.user), pk=pk)` plutôt que `get_object_or_404(Task, pk=pk)`. Conséquence : pas d'accès par manipulation d'identifiant dans l'URL. C'est la bonne pratique et elle est appliquée sans exception dans `tasks`, `documents`, `visitors` et `meetings`.

2. **Actions destructives protégées.** Toutes les suppressions et la sortie visiteur sont en `@require_POST` avec jeton CSRF, et les redirections `next` passent par `safe_next_url()` qui s'appuie sur `url_has_allowed_host_and_scheme` — pas de redirection ouverte.

3. **Documents jamais servis en direct.** `/media/` renvoie `404` dans Nginx et le téléchargement passe par une vue Django authentifiée qui vérifie la visibilité (`documents/views.py:174`). Cohérence complète entre les deux couches.

4. **Uploads maîtrisés.** Extension et taille validées côté serveur (`documents/forms.py:44`), nom de fichier reconstruit à partir d'un `slugify` du nom d'origine et d'un suffixe UUID (`documents/models.py:11`) — aucune possibilité de traversée de répertoire ni de collision.

5. **Rappels de réunion idempotents.** `dispatch_due_meeting_reminders()` (`meetings/services.py:69`) verrouille chaque envoi par un `UPDATE ... WHERE rappel_xx_envoye_at IS NULL` et n'envoie que si la mise à jour a affecté une ligne. Même avec plusieurs workers Gunicorn en parallèle, pas de notification en double. Le mécanisme est correct — c'est son déclenchement qui pose problème (§4.2).

6. **En-têtes de sécurité HTTP complets** côté Nginx : CSP, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`, `Permissions-Policy`, redirection 80→443.

7. **`.dockerignore` correct.** `.env`, `db.sqlite3`, `media/` et `docker/nginx/certs` sont exclus de l'image : les secrets ne sont pas embarqués dans l'artefact Docker, ils sont injectés à l'exécution via `env_file`. Ce détail est souvent raté, il est juste ici.

8. **Documentation d'exploitation réelle.** `docs/EXPLOITATION.md`, unité systemd, script de sauvegarde, procédure de résolution de nom `.local`. Rare à ce stade d'un projet.

---

## 4. Problèmes identifiés

### 4.1 Bloquants

**B1 — Aucun contrôle de version**
Le répertoire n'est pas un dépôt Git (`git status` → *not a git repository*). Il n'existe ni historique, ni branche, ni possibilité de revenir sur une modification, ni sauvegarde du code hors du poste de travail. Un `.gitignore` a été rédigé mais n'a jamais servi. C'est le risque numéro un du projet, avant tout problème technique : une suppression accidentelle du dossier fait disparaître l'application.

**B2 — Mots de passe de bases de données restés aux valeurs d'exemple**
Dans `.env` réel :
```
POSTGRES_PASSWORD=change-this-postgres-password
NEXTCLOUD_POSTGRES_PASSWORD=change-this-nextcloud-password
```
Le README (§ « Variables sensibles ») indique explicitement qu'il faut les remplacer. Ce n'a pas été fait. `SECRET_KEY` et `NEXTCLOUD_ADMIN_PASSWORD`, eux, ont bien des valeurs aléatoires. À corriger avant toute mise en service, avec rotation du mot de passe PostgreSQL dans les deux conteneurs.

**B3 — Clé privée TLS présente dans l'arborescence, partiellement ignorée**
`docker/nginx/certs/` contient `dges-local.key` et **`dges-local.key.bak`**. Le `.gitignore` couvre `docker/nginx/certs/*.key` mais **pas `*.bak`**. Dès la création du dépôt Git (B1), la copie de sauvegarde de la clé privée serait versionnée. À corriger en même temps que B1 : supprimer les `.bak` et élargir le motif à `docker/nginx/certs/*`.

**B4 — Fuseau horaire en UTC**
`settings.py:153` : `TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "UTC")`, et `DJANGO_TIME_ZONE` n'est défini ni dans `.env` ni dans `.env.example`. L'application tourne donc en UTC.

Or toute la logique métier raisonne en jour et heure **locaux** : « visiteurs du jour » (`heure_entree__date=timezone.localdate()`), « documents du jour », réunions du jour et de la semaine, tâches en retard (`date_limite < timezone.localdate()`), affichage des heures d'entrée/sortie et de réunion, libellés de compte à rebours.

Conséquences concrètes pour l'utilisateur : heures affichées décalées d'une heure (Kinshasa, UTC+1), et bascule de journée erronée — un visiteur enregistré à 00h30 heure locale apparaît dans le registre de la veille. C'est le défaut fonctionnel le plus visible de l'existant, et le plus simple à corriger (`DJANGO_TIME_ZONE=Africa/Kinshasa` dans `.env`).

### 4.2 Majeurs

**M1 — Aucune pagination**
Aucune occurrence de `Paginator` dans le projet. Les vues liste visiteurs, tâches, documents et réunions renvoient l'intégralité du queryset au gabarit. Le registre des visiteurs grossit de plusieurs lignes par jour ouvré et n'est jamais purgé : la page deviendra lente puis inutilisable en quelques mois d'exploitation. La vue kanban est le cas le plus lourd — elle déclenche une requête par colonne de statut (7 requêtes) sans aucune limite de lignes.

**M2 — Les rappels de réunion dépendent du trafic HTTP**
`dispatch_due_meeting_reminders()` est appelé depuis `core/context_processors.py:40`, c'est-à-dire **à chaque page affichée par chaque utilisateur connecté**, plus explicitement dans `dashboard/views.py:22`, `meetings/views.py:131` et `:148`.

Deux conséquences :

- *Rappels non envoyés.* Si aucun agent ne navigue dans la fenêtre concernée, le rappel ne part jamais. Le rappel « 1 heure avant » ne cible que les réunions situées entre `now+15min` et `now+60min` : passé ce créneau de 45 minutes, la réunion n'est plus sélectionnée et le rappel est définitivement perdu. Le rappel « 15 minutes » a une fenêtre de 15 minutes seulement. Une réunion à 8h00 alors que les agents se connectent à 8h05 ne déclenche aucun rappel.
- *Écritures en base sur des requêtes GET.* Chaque affichage de page exécute deux requêtes de sélection supplémentaires, et potentiellement des `bulk_create` de notifications, sur un verbe HTTP censé être sans effet de bord.

Le conteneur `nextcloud-cron` existe déjà dans la pile : le correctif consiste à extraire une commande de management (`python manage.py envoyer_rappels_reunions`) et à la planifier (cron, ou timer systemd), puis à retirer l'appel du context processor.

**M3 — Un droit sensible dépend d'un champ de saisie libre**
`core/permissions.py:76` — `can_manage_meetings()` accorde le droit aux rôles DG/secrétariat/administrateur, **ou** si le champ texte libre `UserProfile.fonction` contient l'une des sous-chaînes `personnel`, `ressources humaines`, `ressource humaine`, `rh`.

Problèmes :

- Le droit est accordé ou retiré par une faute de frappe dans un champ descriptif. « Chargée du Personnel » donne le droit, « Chargée du Personel » ne le donne pas, sans que personne comprenne pourquoi.
- La recherche porte sur des sous-chaînes : toute fonction contenant « personnel » l'obtient, y compris « Gestion du personnel enseignant » ou « Agent — dossiers du personnel », qui n'ont pas nécessairement vocation à convoquer des réunions.
- Le champ est librement modifiable depuis l'admin Django, sans que sa modification apparaisse comme un changement de droits.

Ce droit doit reposer sur un rôle explicite (`ROLE_CHARGE_PERSONNEL`) ou un booléen dédié sur le profil (`peut_gerer_reunions`), pas sur une heuristique textuelle.

**M4 — Le droit « réunions » est trop large et sans notion de propriété**
`get_visible_meetings()` (`meetings/selectors.py:25`) retourne **toutes** les réunions, brouillons compris, dès que `can_manage_meetings(user)` est vrai. Et `meeting_edit`, `meeting_delete` et `meeting_status_update` ne vérifient aucune appartenance : le seul contrôle est `can_manage_meetings`.

Combiné à M3, cela signifie qu'un agent dont la fonction contient « personnel » peut consulter les brouillons de réunion du Cabinet du Directeur Général, les modifier, en changer la date, les marquer « tenue » ou les annuler — avec envoi de notifications à tous les invités. Le périmètre doit être restreint (réunions dont on est organisateur, ou réunions de son service, sauf pour les rôles pleins).

**M5 — Aucune journalisation applicative**
Aucun bloc `LOGGING` dans `settings.py`, aucun usage du module `logging` dans le code. En production, une exception non gérée ne laisse qu'une trace dans les logs Gunicorn du conteneur, non persistés hors du conteneur et non rotés. Aucun moyen d'investiguer un incident signalé la veille.

Par ailleurs le `ActivityLog` applicatif, bien alimenté par `log_activity()` dans toutes les vues d'écriture, n'est consultable que **via l'admin Django** — donc uniquement par les administrateurs. Le tableau de bord n'en affiche que les 8 dernières lignes. Il manque une vue « journal d'activité » filtrable, accessible au DG.

**M6 — Couverture de tests insuffisante sur la couche sensible**
Environ 350 lignes de tests pour 4 100 lignes de code. `accounts/tests.py` et `dashboard/tests.py` sont vides (`# Create your tests here.`).

Ce qui est testé est pertinent (sécurité du téléchargement de documents, sortie visiteur en POST, notifications de réunion, propriétés de retard des tâches). Ce qui **n'est pas** testé est précisément la couche qui porte la sécurité : aucun test sur `core/permissions.py`, aucun test sur les quatre fonctions `get_visible_*()`, aucun test sur la synchronisation rôle → groupe → `is_staff` de `accounts/access.py`. Ce sont les fonctions dont une régression silencieuse ouvrirait un accès non autorisé.

**M7 — Suppression physique sans archivage sur des registres administratifs**
Documents, tâches, visiteurs, réunions et comptes sont supprimés définitivement (`delete()`), sans corbeille ni suppression logique. Sur un registre de visiteurs ou un registre de courriers — pièces à valeur administrative — c'est une perte de traçabilité irréversible. Seul le libellé subsiste dans `ActivityLog`. Le modèle `Document` possède déjà un mécanisme d'archivage (`est_archive`, `Status.ARCHIVE`) : il faudrait le généraliser et réserver la suppression physique à des cas exceptionnels.

### 4.3 Mineurs et dette technique

**m1 — Valeur de repli dangereuse pour `SECRET_KEY`**
`settings.py:33` : en l'absence de `.env`, l'application démarre avec `"intranet-dges-dev-secret-key-change-me"` **et** `DEBUG=True` (`settings.py:37`, défaut `True`). Un déploiement où `.env` serait absent ou mal monté démarrerait donc en mode débogage avec une clé connue, sans aucun signal d'alerte. Il faut lever une erreur au démarrage si `DEBUG` est faux et que `SECRET_KEY` vaut le défaut.

**m2 — HSTS désactivé**
`.env` : `SECURE_HSTS_SECONDS=0` alors que `.env.example` propose `31536000`. C'est le seul avertissement remonté par `manage.py check --deploy` (security.W004). Peu critique en réseau interne avec certificat auto-signé, mais figurait dans la liste des points à traiter du README.

**m3 — `CSRF_TRUSTED_ORIGINS` non défini**
Fonctionne aujourd'hui grâce à `SECURE_PROXY_SSL_HEADER` et à la cohérence des hôtes. Deviendra nécessaire dès qu'un nom d'hôte ou un port supplémentaire sera exposé.

**m4 — `'unsafe-inline'` dans la CSP scripts**
Rendu nécessaire par le script de thème en ligne dans `templates/base.html:8-19`. Contournable en déplaçant ce script dans un fichier statique.

**m5 — Aucune notification hors application**
Aucun paramètre `EMAIL_*` configuré. Les « notifications internes » sont uniquement des lignes en base affichées dans le badge de la barre latérale : l'agent doit être connecté et rafraîchir la page pour les voir. À mettre en cohérence avec l'attente réelle des utilisateurs (mail, ou message Nextcloud Talk).

**m6 — Bascule base de test fragile**
`settings.py:97` : `RUNNING_TESTS = sys.argv[1] == "test"`. Or un répertoire `.pytest_cache/` est présent, donc `pytest` a déjà été utilisé sur ce projet — et dans ce cas la bascule n'opère pas, les tests s'exécutant alors sur la base réelle. À trancher : soit `pytest-django` correctement configuré, soit suppression de `.pytest_cache/` et usage exclusif de `manage.py test`.

**m7 — Code mort et résidus de génération**
- `documents/urls.py:9` définit une route nommée `courriers`, et `documents/views.py:31` teste `resolver_match.url_name == "courriers"` — mais la navigation (`templates/base.html:66`) utilise `{% url 'documents:list' %}?type=courrier`. La route et la branche associée ne sont jamais atteintes.
- Commentaires `# Create your models here.` / `# Create your views here.` résiduels dans 6 fichiers.
- Fichiers `docker/nginx/certs/*.bak` (cf. B3).
- `db.sqlite3` (284 Ko) présent à la racine alors que la production est sous PostgreSQL.

**m8 — Robustesse de la pile Docker**
- Aucun `healthcheck` sur le service `web` ; `nginx` en dépend sans condition de santé → réponses 502 possibles pendant les migrations au démarrage.
- Le conteneur `web` exécute Gunicorn en `root` (pas de directive `USER` dans le `Dockerfile`).
- Unité systemd en `Type=oneshot` avec `TimeoutStartSec=0` : acceptable, mais aucune supervision au-delà du démarrage.

**m9 — Sauvegarde incomplète et non planifiée**
`scripts/ubuntu/backup-intranet-dges.sh` sauvegarde PostgreSQL (base Django) et `media/`, avec rétention 14 jours. Trois manques :
- **aucune planification fournie** (ni cron, ni timer systemd) — le script existe mais rien ne l'exécute ;
- **les volumes Nextcloud ne sont pas sauvegardés** (`nextcloud_data`, `nextcloud_postgres_data`) : la messagerie et ses fichiers ne sont pas couverts ;
- **aucune procédure de restauration documentée ni testée** — une sauvegarde jamais restaurée n'est pas une sauvegarde.

**m10 — Requête supplémentaire à chaque sauvegarde d'utilisateur**
`accounts/signals.py:19` : le signal `post_save` sur `User` exécute un `get_or_create(utilisateur=instance)` à **chaque** enregistrement, y compris les `save(update_fields=...)` déclenchés par `sync_user_role_group`. Fonctionnel (pas de récursion, car la synchronisation ne touche pas le profil), mais fragile : `elif created: ... else: get_or_create(...)` gagnerait à être remplacé par une création explicite à la création seulement.

**m11 — Écarts entre documentation et configuration réelle**
Le README embarque des valeurs de configuration (IP `192.168.100.5`, extrait de `.env` avec `SECURE_HSTS_SECONDS`) qui divergent déjà du `.env` en place (deux IP `192.168.100.5` et `.11`, HSTS à 0). Ces valeurs doivent vivre dans `.env.example` seulement, le README renvoyant vers lui.

**m12 — Fonctions attendues absentes**
Ni recherche transverse, ni export CSV/PDF sur les registres visiteurs et courriers — deux besoins habituels en contexte administratif (transmission d'un registre, archivage papier). Les modules « demandes internes » annoncés en V2 ne sont pas amorcés ; le module « courriers » est couvert de façon minimale par `Document.Type.COURRIER`.

---

## 5. Recommandations, par ordre de priorité

### Avant toute mise en service

1. `git init`, premier commit, dépôt distant ou sauvegarde hors poste. Supprimer les `docker/nginx/certs/*.bak` et élargir le motif `.gitignore` à `docker/nginx/certs/*`. **(B1, B3)**
2. Remplacer `POSTGRES_PASSWORD` et `NEXTCLOUD_POSTGRES_PASSWORD` par des valeurs robustes, avec rotation côté conteneurs. **(B2)**
3. Ajouter `DJANGO_TIME_ZONE=Africa/Kinshasa` dans `.env` et `.env.example`. **(B4)**
4. Faire échouer le démarrage si `DEBUG=0` et `SECRET_KEY` au défaut. **(m1)**
5. Planifier la sauvegarde (timer systemd), y inclure les volumes Nextcloud, et **réaliser une restauration de test**. **(m9)**

### Sprint suivant

6. Extraire les rappels de réunion dans une commande de management planifiée, élargir les fenêtres de rappel, retirer l'appel du context processor. **(M2)**
7. Remplacer l'heuristique textuelle de `can_manage_meetings` par un rôle ou un booléen explicite, et restreindre le périmètre de `get_visible_meetings` / `meeting_edit` / `meeting_delete`. **(M3, M4)**
8. Ajouter la pagination sur les quatre vues liste et borner le kanban. **(M1)**
9. Configurer `LOGGING` (fichier + rotation, hors conteneur) et ajouter une vue « journal d'activité » filtrable. **(M5)**
10. Écrire les tests manquants sur `core/permissions.py`, les quatre `get_visible_*()` et `accounts/access.py`. **(M6)**

### Ensuite

11. Généraliser la suppression logique / l'archivage sur visiteurs, tâches et réunions. **(M7)**
12. Activer HSTS après validation du HTTPS interne, définir `CSRF_TRUSTED_ORIGINS`, sortir le script de thème en ligne pour retirer `'unsafe-inline'`. **(m2, m3, m4)**
13. `healthcheck` sur `web`, utilisateur non privilégié dans le `Dockerfile`. **(m8)**
14. Nettoyage : route `courriers` morte, commentaires résiduels, `db.sqlite3`, `.pytest_cache`. **(m6, m7)**
15. Export CSV/PDF des registres, recherche transverse. **(m12)**
16. Décider du canal de notification hors application (mail ou Nextcloud Talk). **(m5)**

---

## 6. Conclusion

La V1 tient ses promesses fonctionnelles : les sept modules annoncés existent, fonctionnent et sont écrits proprement. Le travail de sécurité déjà réalisé (téléchargement contrôlé des documents, protection CSRF des actions destructives, filtrage de visibilité systématique, en-têtes Nginx) est réel et de bonne qualité — il ne s'agit pas de déclarations de README non suivies d'effet, le code les met effectivement en œuvre.

Ce qui manque relève de l'exploitation d'un service administratif réel : versionner le code, finir la configuration de production, planifier ce qui doit l'être (rappels, sauvegardes), et retirer la sécurité des mains d'un champ de saisie libre. Les quatre points bloquants du §4.1 se corrigent en moins d'une journée et changent qualitativement le niveau de risque du projet.
