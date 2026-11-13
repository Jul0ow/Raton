#!/usr/bin/env python3
"""Télécharge l'archive d'un outil, vérifie sa somme SHA-256 et en extrait un exécutable.

  telecharger.py URL SHA256 MEMBRE DESTINATION

Sert à la construction de l'image d'outillage. Rien n'est extrait si la somme ne
correspond pas. Seul le membre nommé est extrait, et seulement s'il s'agit d'un fichier
ordinaire : ni chemin choisi par l'archive, ni lien.
"""

import hashlib
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request

TAILLE_MAX = 500_000_000


def main(url, attendu, membre, destination):
    with tempfile.TemporaryFile() as f:
        with urllib.request.urlopen(url, timeout=300) as reponse:
            lus = 0
            while bloc := reponse.read(1 << 20):
                lus += len(bloc)
                if lus > TAILLE_MAX:
                    sys.exit(f"{url} : archive de plus de {TAILLE_MAX // 1_000_000} Mo")
                f.write(bloc)
        f.seek(0)
        somme = hashlib.sha256()
        while bloc := f.read(1 << 20):
            somme.update(bloc)
        if somme.hexdigest() != attendu:
            sys.exit(f"{url} : somme SHA-256 inattendue {somme.hexdigest()}, attendue {attendu}")
        f.seek(0)
        with tarfile.open(fileobj=f, mode="r:gz") as archive:
            info = archive.getmember(membre)
            if not info.isreg():
                sys.exit(f"{url} : {membre} n'est pas un fichier ordinaire")
            with archive.extractfile(info) as source, open(destination, "wb") as cible:
                shutil.copyfileobj(source, cible)
    os.chmod(destination, 0o755)
    print(f"{destination} : somme vérifiée ({attendu[:12]}…)")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    main(*sys.argv[1:])
