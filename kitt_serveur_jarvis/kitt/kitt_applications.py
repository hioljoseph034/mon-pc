"""Ouverture des applications installees, a la demande de l'utilisateur uniquement.

Garde-fous :
- Les applications sont DECOUVERTES (menu Demarrer sous Windows, lanceurs .desktop sous Linux)
  ou ajoutees a la main avec un chemin qui doit exister. KITT ne construit jamais de commande
  a partir du texte : il lance seulement ce qu'il a trouve.
- Les outils d'administration, d'installation et les terminaux sont exclus.
- Le programme est lance sans shell, avec une liste d'arguments vide.
- Chaque ouverture est confirmee par l'utilisateur (dans kitt_skills).
"""
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import kitt_securite as sec

MOTS_INTERDITS = {"cmd", "powershell", "pwsh", "regedit", "gpedit", "msconfig", "mmc", "bash", "sh",
                  "zsh", "wsl", "terminal", "console", "shell", "setup", "install", "installer",
                  "uninstall", "desinstaller", "desinstallation", "update", "diskpart", "bcdedit",
                  "services", "taskschd",
                  # noms francais des memes outils (Windows en francais)
                  "commande", "commandes", "registre", "strategie", "taches", "pare", "feu", "configuration"}
SUFFIXES_WINDOWS = (".lnk", ".exe")


def dossiers_recherche():
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        programdata = os.environ.get("PROGRAMDATA", "")
        return [Path(appdata) / "Microsoft/Windows/Start Menu/Programs",
                Path(programdata) / "Microsoft/Windows/Start Menu/Programs"]
    return [Path("/usr/share/applications"), Path.home() / ".local/share/applications"]


def est_interdit(nom):
    mots = set(re.findall(r"[a-z0-9]+", sec.normaliser(nom)))
    return bool(mots & MOTS_INTERDITS)


def _nom_lanceur_linux(chemin):
    """Renvoie le nom affiche d'un fichier .desktop, ou None si l'entree est cachee."""
    try:
        texte = Path(chemin).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if re.search(r"^(NoDisplay|Hidden)\s*=\s*true", texte, re.MULTILINE | re.IGNORECASE):
        return None
    m = re.search(r"^Name\s*=\s*(.+)$", texte, re.MULTILINE)
    return m.group(1).strip() if m else Path(chemin).stem


DUREE_CACHE = 600                 # secondes : le menu Demarrer n'est pas relu a chaque commande
_CACHE = {}


def decouvrir(dossiers=None):
    """{nom normalise: (nom affiche, cible)}. Le resultat est garde DUREE_CACHE secondes par dossier."""
    dossiers = list(dossiers) if dossiers is not None else dossiers_recherche()
    cle = tuple(str(d) for d in dossiers)
    maintenant = time.time()
    if cle in _CACHE and maintenant - _CACHE[cle][0] < DUREE_CACHE:
        return _CACHE[cle][1]
    trouves = _scanner(dossiers)
    _CACHE[cle] = (maintenant, trouves)
    return trouves


def _scanner(dossiers):
    trouves = {}
    for dossier in dossiers:
        if not dossier.is_dir():
            continue
        for chemin in dossier.rglob("*"):
            if chemin.is_symlink() or not chemin.is_file():
                continue
            if chemin.suffix.lower() == ".desktop":
                nom = _nom_lanceur_linux(chemin)
            elif chemin.suffix.lower() in SUFFIXES_WINDOWS:
                nom = chemin.stem
            else:
                continue
            if not nom or est_interdit(nom):
                continue
            trouves.setdefault(sec.normaliser(nom), (nom, str(chemin)))
    return trouves


def applications_perso():
    return {sec.normaliser(n): (n, c) for n, c in sec.charger_config().get("applications_perso", {}).items()}


def trouver(nom):
    """('ok', nom affiche, cible) | ('ambigu', [noms]) | ('rien', None, None)."""
    cle = sec.normaliser(nom).strip()
    if not cle:
        return ("rien", None, None)
    entrees = {**decouvrir(), **applications_perso()}
    if cle in entrees:
        affiche, cible = entrees[cle]
        return ("ok", affiche, cible)
    proches = [k for k in entrees if len(cle) >= 3 and (cle in k or k in cle)]
    if len(proches) == 1:
        affiche, cible = entrees[proches[0]]
        return ("ok", affiche, cible)
    if len(proches) > 1:
        return ("ambigu", sorted(entrees[k][0] for k in proches)[:6], None)
    return ("rien", None, None)


def lancer(cible):
    """Lance la cible sans shell. Renvoie True si le lancement a ete tente."""
    if sys.platform == "win32":
        os.startfile(cible)                              # ouvre le raccourci ou l'executable
    elif cible.endswith(".desktop"):
        gtk = shutil.which("gtk-launch")
        if not gtk:
            raise OSError("gtk-launch est absent")
        subprocess.Popen([gtk, Path(cible).stem])
    else:
        subprocess.Popen([cible])
    return True


def ajouter_perso(nom, chemin):
    """Ajoute une application a la main. Renvoie un message."""
    nom = sec.nettoyer_texte(nom, 60)
    if not nom or est_interdit(nom):
        return "Je n'ajoute pas cet outil : il relève de l'administration du système."
    p = Path(chemin.strip().strip('"'))
    if not p.is_absolute():
        return "Donnez le chemin complet de l'application, par exemple C:\\Program Files\\App\\app.exe."
    if not p.is_file():
        return "Je ne trouve aucun fichier à cet emplacement."
    if sys.platform == "win32" and p.suffix.lower() not in SUFFIXES_WINDOWS:
        return "Seuls les fichiers .exe ou .lnk peuvent être ajoutés."
    if sys.platform != "win32" and not os.access(p, os.X_OK):
        return "Ce fichier n'est pas exécutable."
    cfg = sec.charger_config()
    perso = dict(cfg.get("applications_perso", {}))
    perso[nom] = str(p)
    cfg["applications_perso"] = perso
    sec.sauver_config(cfg)
    return f"Application « {nom} » ajoutée."
