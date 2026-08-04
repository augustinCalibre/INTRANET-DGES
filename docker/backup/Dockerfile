# Image du service de sauvegarde.
#
# Elle part de la meme image que la base : pg_dump doit etre de la meme version
# majeure que le serveur PostgreSQL, faute de quoi le dump est refuse.
#
# On y ajoute zip et unzip : chaque sauvegarde est une archive unique, qu'un
# poste Windows ouvre d'un double-clic sans rien installer.
#
# unzip est installe explicitement plutot que de s'en remettre a celui de
# BusyBox : la restauration verifie l'integrite de l'archive avant d'y toucher
# (unzip -t), et cette verification doit etre celle de l'outil complet.
FROM postgres:16-alpine

RUN apk add --no-cache zip unzip

COPY sauvegarde.sh /usr/local/bin/sauvegarde.sh
COPY restauration.sh /usr/local/bin/restauration.sh
COPY planificateur.sh /usr/local/bin/planificateur.sh
RUN chmod +x /usr/local/bin/sauvegarde.sh \
             /usr/local/bin/restauration.sh \
             /usr/local/bin/planificateur.sh

ENTRYPOINT ["/usr/local/bin/planificateur.sh"]
