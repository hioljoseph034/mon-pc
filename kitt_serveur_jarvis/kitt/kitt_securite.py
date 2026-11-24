"""Securite de KITT : configuration, Internet sous controle, validation des entrees.

Regles appliquees partout dans le projet :
- Internet est coupe par defaut. Un service (meteo, youtube, whatsapp) ne peut etre
  joint que s'il a ete active explicitement, avec confirmation.
- Seules les adresses https des services listes dans SERVICES_RESEAU sont autorisees,
  sans redirection vers un autre site.
- Toute entree (nom de skill, numero, texte) est verifiee avant usage.
- Les fichiers de KITT sont prives (droits 600 sous Linux/macOS).
"""
import json
import os
import re
import time
import unicodedata
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

DOSSIER = Path.home() / ".kitt"
CONFIG = DOSSIER / "config.json"
DOSSIER_SKILLS = DOSSIER / "skills"
INDICATIF = "+237"

# Service -> seuls domaines https que KITT a le droit de joindre pour ce service.
SERVICES_RESEAU = {
    "meteo": ("api.open-meteo.com",),
    "youtube": ("www.youtube.com",),
    "whatsapp": ("web.whatsapp.com",),
    "labo_web": ("fr.wikipedia.org", "en.wikipedia.org"),   # recherche du labo : Wikipédia seulement
}

CONFIG_PAR_DEFAUT = {
    "prenom": "Michael",
    # Coordonnees de Batouri : a verifier pour votre ville, modifiables dans config.json.
    "ville": {"nom": "Batouri", "latitude": 4.4333, "longitude": 14.3667},
    "reseau": {service: False for service in SERVICES_RESEAU},
    # Jeux : nom -> chemin du programme. Renseigne par l'utilisateur, jamais par KITT.
    "jeux": {},
    # Initiatives : KITT peut signaler une situation de lui-meme (jamais agir seul).
    "initiatives": {"activees": True, "pause_minutes": 90, "pause_auto": True},
    # Modele local Ollama utilise pour la discussion et la redaction (ex. "mistral", "tinyllama-kitt").
    "modele_llm": "qwen2.5-kitt",
    # Ton des messages : « sobre », « chaleureux » ou « espiegle ».
    "ton": "chaleureux",
    # KITT peut proposer une idee de lui-meme (une fois par jour au plus, a un moment calme).
    "idees_spontanees": True,
    # Entrees au demarrage : voix (micro) et gestes (webcam). Gestes coupes par defaut (camera).
    "entrees": {"voix": True, "gestes": False},
    # Applications ajoutees a la main : nom -> chemin complet (ajoutees par l'utilisateur).
    "applications_perso": {},
}


def normaliser(texte):
    """Minuscules, sans accents, sans tirets ni apostrophes typographiques."""
    s = (texte or "").lower().replace("\u2019", "'").replace("-", " ")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


# ---------- configuration ----------
def ecrire_prive(chemin, texte):
    """Ecrit un fichier lisible par son seul utilisateur. L'ecriture est atomique : une coupure
    pendant l'ecriture ne laisse jamais un fichier a moitie ecrit (fichier temporaire puis remplacement)."""
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    temporaire = chemin.with_name(chemin.name + ".tmp")
    fd = os.open(temporaire, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(texte)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporaire, chemin)


AVERTISSEMENTS = []      # problemes de config.json, affiches au demarrage (et sans doublon)


def avertissements():
    return list(AVERTISSEMENTS)


def _avertir(message):
    if message not in AVERTISSEMENTS:
        AVERTISSEMENTS.append(message)


def _verifier_config(donnees):
    """Signale ce qui est inconnu ou invalide dans config.json. La valeur par defaut reste utilisee."""
    for cle in donnees:
        if cle not in CONFIG_PAR_DEFAUT:
            _avertir(f"clé inconnue « {cle} » dans config.json (faute de frappe ?) : ignorée")

    def invalide(cle, attendu):
        _avertir(f"« {cle} » invalide dans config.json ({attendu}) : valeur par défaut utilisée")

    def nombre(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    if "prenom" in donnees and not isinstance(donnees["prenom"], str):
        invalide("prenom", "un texte")
    if "ville" in donnees:
        v = donnees["ville"]
        if not (isinstance(v, dict) and nombre(v.get("latitude")) and nombre(v.get("longitude"))):
            invalide("ville", "latitude et longitude en nombres")
    for cle in ("reseau", "jeux", "applications_perso", "initiatives", "entrees"):
        if cle in donnees and not isinstance(donnees[cle], dict):
            invalide(cle, "un objet entre accolades")
    if isinstance(donnees.get("reseau"), dict):
        for s_ in donnees["reseau"]:
            if s_ not in SERVICES_RESEAU:
                _avertir(f"service « {s_} » inconnu dans « reseau » : ignoré")
    if "idees_spontanees" in donnees and not isinstance(donnees["idees_spontanees"], bool):
        invalide("idees_spontanees", "true ou false")
    if "ton" in donnees and donnees["ton"] not in ("sobre", "chaleureux", "espiegle"):
        invalide("ton", "sobre, chaleureux ou espiegle")
    if "modele_llm" in donnees and not (isinstance(donnees["modele_llm"], str)
                                        and re.fullmatch(r"[A-Za-z0-9_.:\-]{1,64}", donnees["modele_llm"].strip())):
        invalide("modele_llm", "un nom de modèle sans espace")
    ini = donnees.get("initiatives")
    if isinstance(ini, dict):
        pm = ini.get("pause_minutes")
        if "pause_minutes" in ini and not (isinstance(pm, int) and not isinstance(pm, bool)):
            invalide("initiatives.pause_minutes", "un nombre entier")
        for cle in ("activees", "pause_auto"):
            if cle in ini and not isinstance(ini[cle], bool):
                invalide(f"initiatives.{cle}", "true ou false")
    ent = donnees.get("entrees")
    if isinstance(ent, dict):
        for cle in ("voix", "gestes"):
            if cle in ent and not isinstance(ent[cle], bool):
                invalide(f"entrees.{cle}", "true ou false")


def _lire_config(brut):
    """Interprete le contenu brut de config.json (bytes, ou None si le fichier est absent)."""
    cfg = json.loads(json.dumps(CONFIG_PAR_DEFAUT))
    if brut is None:
        donnees = {}                                  # pas de fichier : normal
    else:
        try:
            donnees = json.loads(brut.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            _avertir("config.json n'est pas lisible (JSON invalide ?) : valeurs par défaut utilisées")
            donnees = {}
    if not isinstance(donnees, dict):
        _avertir("config.json doit contenir un objet entre accolades : valeurs par défaut utilisées")
        donnees = {}
    else:
        _verifier_config(donnees)
    if isinstance(donnees.get("prenom"), str):
        cfg["prenom"] = donnees["prenom"][:40]
    ville = donnees.get("ville")
    if isinstance(ville, dict):
        try:
            cfg["ville"] = {"nom": str(ville.get("nom", cfg["ville"]["nom"]))[:40],
                            "latitude": float(ville["latitude"]),
                            "longitude": float(ville["longitude"])}
        except (KeyError, TypeError, ValueError):
            pass
    reseau = donnees.get("reseau") if isinstance(donnees.get("reseau"), dict) else {}
    cfg["reseau"] = {s: bool(reseau.get(s, False)) for s in SERVICES_RESEAU}
    jeux = donnees.get("jeux") if isinstance(donnees.get("jeux"), dict) else {}
    cfg["jeux"] = {normaliser(k): v for k, v in jeux.items() if isinstance(v, str)}
    apps = donnees.get("applications_perso") if isinstance(donnees.get("applications_perso"), dict) else {}
    cfg["applications_perso"] = {k[:60]: v for k, v in apps.items() if isinstance(v, str) and k.strip()}
    ini = donnees.get("initiatives") if isinstance(donnees.get("initiatives"), dict) else {}
    try:
        pause = int(ini.get("pause_minutes", 90))
    except (TypeError, ValueError):
        pause = 90
    if isinstance(donnees.get("idees_spontanees"), bool):
        cfg["idees_spontanees"] = donnees["idees_spontanees"]
    ton = donnees.get("ton")
    if ton in ("sobre", "chaleureux", "espiegle"):
        cfg["ton"] = ton
    entrees = donnees.get("entrees") if isinstance(donnees.get("entrees"), dict) else {}
    cfg["entrees"] = {"voix": bool(entrees.get("voix", True)), "gestes": bool(entrees.get("gestes", False))}
    modele = donnees.get("modele_llm")
    if isinstance(modele, str) and re.fullmatch(r"[A-Za-z0-9_.:\-]{1,64}", modele.strip()):
        cfg["modele_llm"] = modele.strip()
    cfg["initiatives"] = {"activees": bool(ini.get("activees", True)),
                          "pause_minutes": min(max(pause, 30), 240),
                          "pause_auto": bool(ini.get("pause_auto", True))}
    return cfg


_CACHE_CONFIG = {"brut": None, "cfg": None}


def charger_config():
    """Configuration courante. Le fichier n'est reanalyse que s'il a change (comparaison de son contenu)."""
    try:
        brut = CONFIG.read_bytes()
    except FileNotFoundError:
        brut = None
    except OSError:
        brut = b"\x00illisible"
    if _CACHE_CONFIG["cfg"] is None or brut != _CACHE_CONFIG["brut"]:
        _CACHE_CONFIG["cfg"] = _lire_config(brut)
        _CACHE_CONFIG["brut"] = brut
    return json.loads(json.dumps(_CACHE_CONFIG["cfg"]))


def sauver_config(cfg):
    ecrire_prive(CONFIG, json.dumps(cfg, ensure_ascii=False, indent=2))


def choisir_entrees(argv, par_defaut):
    """Entrees de la session : les options de ligne de commande l'emportent sur config.json.
    --voix / --sans-voix ; --gestes / --sans-gestes."""
    voix = bool(par_defaut.get("voix", True))
    gestes = bool(par_defaut.get("gestes", False))
    if "--sans-voix" in argv:
        voix = False
    elif "--voix" in argv:
        voix = True
    if "--sans-gestes" in argv:
        gestes = False
    elif "--gestes" in argv:
        gestes = True
    return {"voix": voix, "gestes": gestes}


def reseau_active(service):
    return service in SERVICES_RESEAU and charger_config()["reseau"].get(service, False)


# ---------- reseau ----------
def url_autorisee(service, url):
    """Vrai seulement si le service est active ET que l'adresse est un https du service."""
    if not reseau_active(service):
        return False
    p = urlparse(url)
    return p.scheme == "https" and p.hostname in SERVICES_RESEAU[service] and not p.username


class _SansRedirection(urllib.request.HTTPRedirectHandler):
    """Une redirection pourrait mener vers un autre site : on ne la suit pas."""
    def redirect_request(self, *args, **kwargs):
        return None


_OUVREUR = urllib.request.build_opener(_SansRedirection)


def requete_json(service, url, timeout=8):
    if not url_autorisee(service, url):
        raise PermissionError(f"Internet n'est pas autorisé pour « {service} ».")
    req = urllib.request.Request(url, headers={"User-Agent": "KITT"})
    with _OUVREUR.open(req, timeout=timeout) as r:
        return json.loads(r.read(200_000).decode("utf-8"))


# ---------- validation des entrees ----------
def nom_valide(nom):
    """2 a 32 caracteres : lettre minuscule, puis lettres sans accent, chiffres ou _."""
    return re.fullmatch(r"[a-z][a-z0-9_]{1,31}", nom or "") is not None


def normaliser_numero(brut, indicatif=INDICATIF):
    """Renvoie +237... (ou autre indicatif) si le numero est plausible, sinon None."""
    s = re.sub(r"[ .\-()]", "", brut or "")
    if s.startswith("00"):
        s = "+" + s[2:]
    if not s.startswith("+"):
        s = indicatif + s.lstrip("0")
    return s if re.fullmatch(r"\+\d{8,15}", s) else None


def nettoyer_texte(texte, limite=500):
    """Retire les caracteres de controle et limite la longueur."""
    propre = "".join(c for c in (texte or "") if c.isprintable() or c in "\n")
    return propre.strip()[:limite]


def chemin_dans(base, nom):
    """Chemin base/nom.json, refuse tout nom qui sortirait du dossier."""
    if not nom_valide(nom):
        raise ValueError("nom de skill invalide")
    chemin = (base / f"{nom}.json").resolve()
    if chemin.parent != base.resolve():
        raise ValueError("chemin hors du dossier des skills")
    return chemin


class Limiteur:
    """Au plus `max_par_heure` actions par heure (ex. envois WhatsApp).
    Avec `fichier`, les dates sont sauvegardees : redemarrer KITT ne remet pas le compteur a zero.
    Si la sauvegarde echoue, l'action est refusee (on ne contourne pas la limite)."""

    def __init__(self, max_par_heure, fichier=None):
        self.max = max_par_heure
        self.fichier = Path(fichier) if fichier else None
        self.dates = self._charger()

    def _charger(self):
        if not self.fichier:
            return []
        try:
            donnees = json.loads(self.fichier.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(donnees, list):
            return []
        return [float(d) for d in donnees if isinstance(d, (int, float))]

    def autorise(self):
        maintenant = time.time()
        self.dates = [d for d in self.dates if maintenant - d < 3600]
        if len(self.dates) >= self.max:
            return False
        self.dates.append(maintenant)
        if self.fichier:
            try:
                ecrire_prive(self.fichier, json.dumps(self.dates))
            except OSError:
                self.dates.pop()
                return False
        return True
