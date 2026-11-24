"""Skills de KITT : installeur, modules integres et recettes utilisateur.

Principes :
- Un skill n'est actif qu'une fois installe (un manifeste JSON dans ~/.kitt/skills).
- Aucun code n'est telecharge, importe ni execute depuis le dossier des skills.
  Un skill cree par l'utilisateur est une « recette » : des declencheurs et une reponse.
- Internet n'est utilise que pour les services actives (voir kitt_securite).
- Toute action externe (appel, message WhatsApp, activation d'Internet) est confirmee.
"""
import json
import random
import re
import subprocess
import urllib.parse
import webbrowser
from pathlib import Path

import kitt_securite as sec
import kitt_ton as ton
import kitt_initiatives as ki
import kitt_applications as ka
import kitt_calcul as kc
import kitt_labo3d as kl3
import kitt_idees as kidees

CATALOGUE = {
    "meteo": {"titre": "Météo (Internet)", "reseau": "meteo",
              "declencheurs": ["meteo", "il fait combien", "temps qu'il fait"]},
    "blague": {"titre": "Blagues", "reseau": None, "declencheurs": ["blague", "rigole"]},
    "labo3d": {"titre": "Laboratoire 3D (simulation dans le navigateur)", "reseau": None,
               "declencheurs": ["simulation 3d", "simule en 3d", "labo 3d", "en 3d", "propose labo"]},
    "physique": {"titre": "Physique : ressort, circuit RC, réfraction, conversions", "reseau": None,
                 "declencheurs": ["laboratoire ressort", "laboratoire circuit", "laboratoire refraction",
                                  "laboratoire réfraction", "convertis", "convertir"]},
    "idees": {"titre": "Idées (propositions variées)", "reseau": None,
              "declencheurs": ["donne moi des idees", "donne-moi des idees", "idees pour", "des idees"]},
    "avis": {"titre": "Avis (point de vue motivé)", "reseau": None,
             "declencheurs": ["que penses-tu", "que pense tu", "ton avis", "qu'en penses-tu"]},
    "calcul": {"titre": "Calculatrice (calculs exacts)", "reseau": None,
               "declencheurs": ["combien font", "combien fait", "calcule", "calcul"]},
    "echecs": {"titre": "Échecs", "reseau": None, "declencheurs": ["echecs"]},
    "jeux": {"titre": "Lancer vos jeux", "reseau": None,
             "declencheurs": ["joue a", "lance le jeu", "jeux"]},
    "youtube": {"titre": "YouTube (Internet)", "reseau": "youtube", "declencheurs": ["youtube"]},
    "appel": {"titre": "Appels via votre téléphone Android (adb, sans Internet)", "reseau": None,
              "declencheurs": ["appelle", "appel"]},
    "whatsapp": {"titre": "WhatsApp (Internet)", "reseau": "whatsapp",
                 "declencheurs": ["whatsapp", "envoie un message"]},
}

BLAGUES = [
    "Pourquoi KITT déteste la pluie ? Il a peur de rouiller 😅",
    "Je suis plus rapide qu'une moto à Yaoundé !",
    "Je ne dors jamais, Michael, je te surveille.",
]

_H = {}                       # fonctions fournies par kitt_complet : skill(), PASSE et la liste SKILLS
_LIMITE_WHATSAPP = sec.Limiteur(10, sec.DOSSIER / "limite_whatsapp.json")


# ============================================================
# 1. INSTALLEUR : manifestes JSON, jamais de code
# ============================================================
def lire_manifeste(nom):
    try:
        donnees = json.loads(sec.chemin_dans(sec.DOSSIER_SKILLS, nom).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(donnees, dict) and donnees.get("type") in ("interne", "recette"):
        return donnees
    return None


def installes():
    if not sec.DOSSIER_SKILLS.is_dir():
        return set()
    return {p.stem for p in sec.DOSSIER_SKILLS.glob("*.json")
            if sec.nom_valide(p.stem) and lire_manifeste(p.stem)}


def installer(nom):
    nom = sec.normaliser(nom).strip()
    if nom not in CATALOGUE:
        return "Skill inconnu. Disponibles : " + ", ".join(CATALOGUE) + "."
    sec.ecrire_prive(sec.chemin_dans(sec.DOSSIER_SKILLS, nom),
                     json.dumps({"type": "interne", "version": 1}))
    msg = f"Skill « {nom} » installé : {CATALOGUE[nom]['titre']}."
    service = CATALOGUE[nom]["reseau"]
    if service and not sec.reseau_active(service):
        msg += f" Il faut aussi autoriser Internet : dites « active internet {service} »."
    return msg


def desinstaller(nom):
    nom = sec.normaliser(nom).strip()
    if not sec.nom_valide(nom):
        return "Nom de skill invalide."
    d = lire_manifeste(nom)
    try:
        sec.chemin_dans(sec.DOSSIER_SKILLS, nom).unlink()
        if d and d.get("type") == "recette":
            _debrancher_recette(nom)
    except FileNotFoundError:
        return f"Le skill « {nom} » n'est pas installé."
    except ValueError:
        return "Nom de skill invalide."
    return f"Skill « {nom} » désinstallé."


def activer_reseau(service, actif):
    if service not in sec.SERVICES_RESEAU:
        return "Service inconnu. Choix : " + ", ".join(sec.SERVICES_RESEAU) + "."
    cfg = sec.charger_config()
    cfg["reseau"][service] = bool(actif)
    sec.sauver_config(cfg)
    return f"Internet {'activé' if actif else 'coupé'} pour {service}."


# ============================================================
# 2. RECETTES : skills créés par l'utilisateur (données uniquement)
# ============================================================
def valider_recette(nom, declencheurs, reponse):
    nom = sec.normaliser(nom).strip()
    if not sec.nom_valide(nom):
        raise ValueError("nom : 2 à 32 caractères, lettres sans accent, chiffres ou _ "
                         "(ex. blague_du_jour).")
    if nom in CATALOGUE:
        raise ValueError("ce nom est réservé à un skill intégré.")
    decl = []
    for d in declencheurs:
        d = sec.normaliser(d).strip()
        if not d:
            continue
        if not re.fullmatch(r"[a-z0-9' ]{3,40}", d):
            raise ValueError(f"déclencheur invalide « {d} » : lettres, chiffres, espaces "
                             "et apostrophes seulement.")
        decl.append(d)
    if not 1 <= len(decl) <= 5:
        raise ValueError("indiquez de 1 à 5 déclencheurs, séparés par des virgules.")
    rep = sec.nettoyer_texte(reponse, 300)
    if not rep:
        raise ValueError("la réponse est vide.")
    return {"type": "recette", "version": 1, "declencheurs": decl, "reponse": rep}


def creer_recette(nom, declencheurs, reponse):
    try:
        donnees = valider_recette(nom, declencheurs, reponse)
    except ValueError as e:
        return f"Impossible de créer le skill : {e}"
    nom = sec.normaliser(nom).strip()
    sec.ecrire_prive(sec.chemin_dans(sec.DOSSIER_SKILLS, nom),
                     json.dumps(donnees, ensure_ascii=False, indent=2))
    _brancher_recette(nom, donnees["declencheurs"])
    return f"Skill « {nom} » créé : je réponds à « {', '.join(donnees['declencheurs'])} »."


def _debrancher_recette(nom):
    """Retire la recette de la liste des skills : ses anciens declencheurs ne repondent plus."""
    liste = _H.get("liste")
    if liste is not None:
        liste[:] = [e for e in liste if e[0] != nom]


def _brancher_recette(nom, declencheurs):
    """Branche la recette sur le moteur. Une recette deja branchee est remplacee : seuls les
    declencheurs actuels restent actifs. Le manifeste est relu a chaque appel."""
    if "skill" not in _H:
        return
    _debrancher_recette(nom)

    def repondre(k, t):
        d = lire_manifeste(nom)
        if not d or d.get("type") != "recette":
            return _H["passe"]
        return d.get("reponse", "")

    _H["skill"](nom, declencheurs)(repondre)


def _recettes_existantes():
    if not sec.DOSSIER_SKILLS.is_dir():
        return
    for p in sorted(sec.DOSSIER_SKILLS.glob("*.json")):
        d = lire_manifeste(p.stem) if sec.nom_valide(p.stem) else None
        if d and d["type"] == "recette":
            try:
                donnees = valider_recette(p.stem, d.get("declencheurs", []), d.get("reponse", ""))
            except ValueError:
                continue            # manifeste altere : ignore plutot que de planter
            _brancher_recette(p.stem, donnees["declencheurs"])


# ============================================================
# 3. CONTACTS : la table « contacts » de la base de KITT (kitt.db)
# ============================================================
def assurer_colonne_telephone(k):
    """Ajoute la colonne telephone a la table existante, une seule fois (migration douce)."""
    colonnes = [r[1] for r in k.mem.exe("PRAGMA table_info(contacts)")]
    if "telephone" not in colonnes:
        k.mem.exe("ALTER TABLE contacts ADD COLUMN telephone TEXT")


def contacts_avec_numero(k):
    """{nom normalise: (nom affiche, numero +237...)} pour les contacts ayant un numero valide."""
    assurer_colonne_telephone(k)
    out = {}
    for nom, tel in k.mem.exe("SELECT nom, telephone FROM contacts "
                              "WHERE telephone IS NOT NULL AND telephone != ''"):
        num = sec.normaliser_numero(tel)
        if num:
            out[sec.normaliser(nom)] = (nom, num)
    return out


def trouver_contact(k, texte):
    """(nom affiche, numero) ou (None, None). Accepte aussi un numero tape dans la phrase."""
    n = sec.normaliser(texte)
    for cle, (nom, num) in sorted(contacts_avec_numero(k).items(), key=lambda x: -len(x[0])):
        if re.search(r"\b" + re.escape(cle) + r"\b", n):
            return nom, num
    m = re.search(r"\+?\d[\d ]{7,16}\d", texte)
    if m:
        num = sec.normaliser_numero(m.group(0))
        if num:
            return num, num
    return None, None


def cmd_numero(k, t):
    """« ajoute le numero de Marc 06 77 12 34 56 » : enregistre le numero dans la table contacts."""
    m = re.search(r"(?i)\bnum[ée]ro\s+(?:de\s+|du\s+|pour\s+)?(.+?)\s+(\+?\d[\d ]{7,18}\d)\s*$", t)
    if not m:
        return "Dites : ajoute le numéro de Marc 06 77 12 34 56."
    num = sec.normaliser_numero(m.group(2))
    if not num:
        return "Ce numéro ne semble pas valide."
    assurer_colonne_telephone(k)
    nom = m.group(1).strip(" ,.").title()
    cle = sec.normaliser(nom)
    existants = {sec.normaliser(n): n for (n,) in k.mem.exe("SELECT nom FROM contacts")}
    if cle in existants:
        nom = existants[cle]
    else:
        k.mem.exe("INSERT INTO contacts (nom, email, telephone) VALUES (?, NULL, NULL)", (nom,))
    k.mem.exe("UPDATE contacts SET telephone = ? WHERE nom = ?", (num, nom))
    return f"Numéro enregistré pour {nom} : {num}."


# ============================================================
# 4. COMMANDES DES SKILLS INTEGRES
# ============================================================
def cmd_installer(k, t):
    mot = sec.normaliser(t).split()[-1] if t.split() else ""
    if mot in ("installe", "skill", "le", "un", ""):
        return "Quel skill installer ? Disponibles : " + ", ".join(CATALOGUE) + "."
    return installer(mot)


def cmd_desinstaller(k, t):
    mot = sec.normaliser(t).split()[-1] if t.split() else ""
    return desinstaller(mot)


def cmd_lister(k, t):
    inst = installes()
    lignes = [f"{'[x]' if nom in inst else '[ ]'} {nom} : {info['titre']}"
              for nom, info in CATALOGUE.items()]
    recettes = sorted(n for n in inst if n not in CATALOGUE)
    if recettes:
        lignes.append("Vos skills créés : " + ", ".join(recettes))
    return "\n".join(lignes)


def cmd_creer(k, t):
    corps = re.split(r"(?i)\bskill\b", t, maxsplit=1)[-1]
    parties = [p.strip() for p in corps.split("|")]
    if len(parties) != 3:
        return ("Format : crée skill nom | déclencheur1, déclencheur2 | réponse. "
                "Exemple : crée skill salut | bonjour, salut | Bonjour Michael !")
    return creer_recette(parties[0], parties[1].split(","), parties[2])


def cmd_initiatives(k, t):
    n = sec.normaliser(t)
    actif = not re.search(r"\bdesactive\b", n)
    cfg = sec.charger_config()
    if re.search(r"\bidees?\b", n):                       # « desactive les idees » : seulement les idees
        cfg["idees_spontanees"] = actif
        sec.sauver_config(cfg)
        return "D'accord, je garde mes idées pour moi." if not actif else "D'accord, je peux de nouveau proposer des idées."
    cfg["initiatives"]["activees"] = actif
    sec.sauver_config(cfg)
    return "D'accord, je signale les situations utiles." if actif else "D'accord, je reste discret."


def cmd_habitudes(k, t):
    return ki.resume(ki.apprendre(k.mem))


_VERBE_OUVRIR = re.compile(r"^\s*(?:kitt[ ,]+)?(?:ouvre|ouvrir|lance|lancer|demarre|demarrer)\b\s*"
                           r"(?:l'|le |la |les |un |une )?(?:application |appli |programme )?", re.IGNORECASE)
_AJOUT_APP = re.compile(r"(?i)l'?\s*application\s+(.+?)\s+((?:[A-Za-z]:[\\/]|/)\S.*)$")


def cmd_ouvrir_app(k, t):
    """Seule une phrase qui COMMENCE par le verbe est une commande : « je lance une reunion » ne compte pas."""
    m = _VERBE_OUVRIR.match(t)
    if not m:
        return _H["passe"]
    nom = t[m.end():].strip(" .!?'\"")
    if not nom:
        return "Quelle application dois-je ouvrir ?"
    if ka.est_interdit(nom):
        return "Je n'ouvre pas les outils d'administration ni les terminaux."
    statut, affiche, cible = ka.trouver(nom)
    if statut == "rien":
        return ton.phrase("app_introuvable", nom=nom)
    if statut == "ambigu":
        return "Plusieurs applications correspondent : " + ", ".join(affiche) + ". Précisez le nom."
    if not k.confirmer(f"J'ouvre {affiche}"):
        return ton.phrase("annule")
    try:
        ka.lancer(cible)
    except OSError:
        return f"Je n'arrive pas à lancer {affiche}."
    return f"{affiche} est lancé."


def cmd_ajouter_app(k, t):
    m = _AJOUT_APP.search(t)
    if not m:
        return ("Dites : ajoute l'application NOM suivi du chemin complet, par exemple : "
                "ajoute l'application Bloc-notes C:\\Windows\\notepad.exe")
    nom, chemin = m.group(1), m.group(2)
    if not k.confirmer(f"J'ajoute « {nom} » avec le chemin {chemin}"):
        return ton.phrase("annule")
    return ka.ajouter_perso(nom, chemin)


def cmd_entrees(k, t):
    n = sec.normaliser(t)
    if re.search(r"\bgestes?\b", n):
        nom = "gestes"
    elif re.search(r"\bvoix\b", n):
        nom = "voix"
    else:
        return "Quoi régler ? Dites : active les gestes, désactive la voix..."
    actif = not re.search(r"\b(desactive|coupe)\b", n)
    return k.regler_entree(nom, actif)


def cmd_reseau(k, t):
    n = sec.normaliser(t)
    service = next((s for s in sec.SERVICES_RESEAU if re.search(r"\b" + s + r"\b", n)), None)
    if not service:
        return "Quel service ? Choix : " + ", ".join(sec.SERVICES_RESEAU) + "."
    actif = not re.search(r"\b(desactive|coupe)\b", n)
    if actif and not k.confirmer(f"J'autorise KITT à contacter {service} sur Internet"):
        return "Très bien, Internet reste coupé."
    return activer_reseau(service, actif)


def cmd_meteo(k, t):
    cfg = sec.charger_config()
    v = cfg["ville"]
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(
        {"latitude": v["latitude"], "longitude": v["longitude"],
         "current": "temperature_2m", "timezone": "auto"})
    try:
        temp = sec.requete_json("meteo", url)["current"]["temperature_2m"]
    except PermissionError:
        return ton.phrase("reseau_requis", service="météo")
    except Exception:
        return "Je n'arrive pas à joindre le service météo."
    return ton.phrase("meteo_ville", ville=v["nom"], temp=f"{temp:g}", prenom=cfg["prenom"],
                      conseil=ton.conseil_meteo(temp))


def cmd_blague(k, t):
    return f"{ton.phrase('blague_intro', prenom=sec.charger_config()['prenom'])} {random.choice(BLAGUES)}"


def cmd_echecs(k, t):
    return ton.phrase("echecs", prenom=sec.charger_config()["prenom"])


def cmd_jeux(k, t):
    jeux = sec.charger_config()["jeux"]
    n = sec.normaliser(t)
    if not jeux:
        return "Aucun jeu configuré. Ajoutez-les dans ~/.kitt/config.json, rubrique « jeux »."
    nom = next((j for j in jeux if re.search(r"\b" + re.escape(j) + r"\b", n)), None)
    if not nom:
        return "Jeux disponibles : " + ", ".join(jeux) + "."
    chemin = Path(jeux[nom])
    if not chemin.is_file():
        return f"Je ne trouve pas le programme de {nom}."
    subprocess.Popen([str(chemin)])          # liste d'arguments, jamais de shell
    return ton.phrase("jeu_lance", nom=nom, prenom=sec.charger_config()["prenom"])


def cmd_youtube(k, t):
    if not sec.reseau_active("youtube"):
        return "YouTube demande Internet. Dites « active internet youtube »."
    recherche = re.sub(r"(?i).*?youtube", "", t, count=1).strip()[:100]
    url = "https://www.youtube.com/results?" + urllib.parse.urlencode({"search_query": recherche})
    if not sec.url_autorisee("youtube", url):
        return "Internet n'est pas autorisé pour YouTube."
    webbrowser.open(url)                     # ouvre le navigateur de l'utilisateur
    return ton.phrase("youtube_ok", recherche=recherche) if recherche else "YouTube ouvert."


def cmd_appel(k, t):
    contact, numero = trouver_contact(k, t)
    if not numero:
        return ton.phrase("sans_numero")
    if not k.confirmer(f"J'appelle {contact} au {numero} avec votre téléphone Android"):
        return ton.phrase("annule")
    try:
        subprocess.run(["adb", "shell", "am", "start", "-a", "android.intent.action.CALL",
                        "-d", f"tel:{numero}"], check=True, timeout=15, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        return "Je n'arrive pas à joindre votre téléphone (adb est-il branché et autorisé ?)."
    return ton.phrase("appel_ok", contact=contact, numero=numero)


def cmd_whatsapp(k, t):
    if not sec.reseau_active("whatsapp"):
        return "WhatsApp demande Internet. Dites « active internet whatsapp »."
    contact, numero = trouver_contact(k, t)
    if not numero:
        return ton.phrase("sans_numero")
    m = re.search(r"\b(?:dis[- ]lui|dis|dit|que)\s*:?\s*(.+)$", t, re.IGNORECASE | re.DOTALL)
    if not m:
        return "Que dois-je écrire ? Exemple : whatsapp à marc dis lui que je suis en route."
    message = sec.nettoyer_texte(re.sub(r"^\s*que\s+", "", m.group(1), flags=re.IGNORECASE), 500)
    if not message:
        return "Le message est vide."
    if not k.confirmer(f"J'envoie sur WhatsApp à {contact} : « {message} »"):
        return ton.phrase("annule")
    if not _LIMITE_WHATSAPP.autorise():
        return "Limite atteinte : 10 messages WhatsApp par heure. Réessayez plus tard."
    try:
        import pywhatkit
    except ImportError:
        return "Installez pywhatkit : pip install pywhatkit"
    try:
        pywhatkit.sendwhatmsg_instantly(numero, message, wait_time=20, tab_close=True)
    except Exception as e:
        return f"Échec de l'envoi WhatsApp : {e}"
    return ton.phrase("whatsapp_ok", contact=contact)


def cmd_calcul(k, t):
    return kc.calculer(t)


def _nombres_fr(texte):
    return [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", texte)]


def cmd_physique(k, t):
    import kitt_labo as kl
    n = sec.normaliser(t).replace("°", "")
    if "ressort" in n:
        nb = _nombres_fr(t)
        if not nb:
            return "Donnez la masse, la raideur et l'amortissement, par exemple : laboratoire ressort masse 2 raideur 50 amortissement 1."
        m, raideur, c = nb[:3] + [1.0, 10.0, 0.0][len(nb[:3]):]          # valeurs manquantes : par defaut, dans l'ordre
        try:
            r = kl.ressort_amorti(m, raideur, c)
        except ValueError as e:
            return f"Je ne peux pas calculer cet oscillateur : {e}."
        base = f"Oscillateur : masse {kc.formater(m)} kg, raideur {kc.formater(raideur)} N/m, amortissement {kc.formater(c)}."
        if r["periode"] is None:
            return base + " L'amortissement est trop fort : il n'y a pas d'oscillation."
        texte = base + f" Période : {kc.formater(round(r['periode'], 3))} s."
        if r["demi_amplitude"] is None:
            return texte + " Sans amortissement, l'oscillation continue indéfiniment."
        return texte + (f" L'amplitude est divisée par deux en {kc.formater(round(r['demi_amplitude'], 3))} s.")
    if "circuit" in n:
        nb = _nombres_fr(t)
        if not nb:
            return "Donnez la résistance, la capacité et la tension, par exemple : laboratoire circuit 1000 0,001 5."
        resistance, capacite, tension = nb[:3] + [1000.0, 0.001, 5.0][len(nb[:3]):]
        try:
            r = kl.circuit_rc(resistance, capacite, tension)
        except ValueError as e:
            return f"Je ne peux pas calculer ce circuit : {e}."
        return (f"Circuit RC : R = {kc.formater(resistance)} ohms, C = {kc.formater(capacite)} farad, "
                f"τ = RC = {kc.formater(round(r['tau'], 6))} s. À t = τ, la tension atteint 63 % de "
                f"{kc.formater(tension)} V, soit {kc.formater(round(r['tension_a_tau'], 3))} V.")
    if "refraction" in n:
        nb = _nombres_fr(t)
        if not nb:
            return "Dites l'angle d'incidence, par exemple : laboratoire réfraction 30 degrés air eau."
        milieux = [m for m in re.findall(r"[a-z]+", n) if m in kl.MILIEUX_INDICE]
        if len(milieux) < 2:
            return f"Milieux reconnus : {', '.join(kl.MILIEUX_INDICE)}. Dites-en deux, par exemple : air eau."
        n1, n2 = kl.MILIEUX_INDICE[milieux[0]], kl.MILIEUX_INDICE[milieux[1]]
        angle = kl.refraction(n1, n2, nb[0])
        if angle is None:
            return f"Réflexion totale : la lumière ne passe pas de {milieux[0]} vers {milieux[1]} sous cet angle."
        return (f"De {milieux[0]} (n = {kc.formater(n1)}) vers {milieux[1]} (n = {kc.formater(n2)}), "
                f"un rayon à {kc.formater(nb[0])}° est transmis à {kc.formater(round(angle, 2))}°.")
    m = re.search(r"([\d.,]+)\s*([a-z/]+)\s+en\s+([a-z/]+)", n)
    if m:
        valeur = float(m.group(1).replace(",", "."))
        try:
            resultat = kl.convertir(valeur, m.group(2), m.group(3))
        except ValueError as e:
            return f"Je ne peux pas convertir : {e}."
        def affiche(u):
            canonique = kl.ALIAS_UNITES.get(u, u)
            return {"c": "°C", "f": "°F", "k": "K"}.get(canonique, canonique)
        return f"{kc.formater(valeur)} {affiche(m.group(2))} = {kc.formater(round(resultat, 4))} {affiche(m.group(3))}."
    if "laboratoire" not in n:
        return _H["passe"]                    # pas une demande de laboratoire : laisser la main aux autres skills
    return ("Dites : laboratoire ressort masse 2 raideur 50 amortissement 1, laboratoire circuit 1000 0,001 5, "
            "laboratoire réfraction 30 degrés air eau, ou convertis 100 km/h en m/s.")


def cmd_idees(k, t):
    return kidees.idees(t, CATALOGUE["idees"]["declencheurs"])


def cmd_avis(k, t):
    return kidees.avis(t, CATALOGUE["avis"]["declencheurs"])


def cmd_labo3d(k, t):
    n = sec.normaliser(t)
    proposee = bool(re.search(r"\bpropos", n))
    if re.search(r"\bchute\b", n):
        scenario = "chute"
    elif re.search(r"\bpendule\b", n):
        scenario = "pendule"
    elif re.search(r"\b(tir|projectile|lance|lancer)\b", n):
        scenario = "tir"
    else:
        return ton.phrase("labo3d_aucun")
    parametres = kl3.parametres_depuis_texte(scenario, t)
    infos = kl3.construire(scenario, parametres)["infos"]
    if proposee and not k.confirmer(f"J'ouvre une simulation de {scenario} dans votre navigateur"):
        return ton.phrase("annule")
    chemin = kl3.generer(scenario, parametres)
    return (f"Simulation ouverte dans votre navigateur. {infos[1].replace('.', ',')}. "
            "Faites-la tourner à la souris, molette pour zoomer.")


_FONCTIONS = {"physique": cmd_physique, "idees": cmd_idees, "avis": cmd_avis, "labo3d": cmd_labo3d, "calcul": cmd_calcul, "meteo": cmd_meteo, "blague": cmd_blague, "echecs": cmd_echecs, "jeux": cmd_jeux,
              "youtube": cmd_youtube, "appel": cmd_appel, "whatsapp": cmd_whatsapp}

COMMANDES = [
    ("skill_installer", ["installe"], cmd_installer),
    ("skill_desinstaller", ["desinstalle"], cmd_desinstaller),
    ("contact_numero", ["ajoute le numero", "ajoute un numero", "enregistre le numero",
                        "ajoute le numéro", "ajoute un numéro"], cmd_numero),
    ("skill_lister", ["mes skills", "liste les skills", "skills disponibles"], cmd_lister),
    ("skill_creer", ["cree un skill", "cree skill", "nouveau skill"], cmd_creer),
    ("reseau", ["active internet", "desactive internet", "coupe internet"], cmd_reseau),
    ("initiatives", ["active les initiatives", "desactive les initiatives",
                     "active les idees", "desactive les idees"], cmd_initiatives),
    ("entrees", ["active les gestes", "desactive les gestes", "coupe les gestes",
                 "active la voix", "desactive la voix", "coupe la voix"], cmd_entrees),
    ("habitudes", ["mes habitudes", "quelles sont mes habitudes", "tes habitudes"], cmd_habitudes),
]


def _protege(nom, fn):
    """Un skill installe repond. Sinon il laisse la main aux suivants."""
    def garde(k, t):
        if lire_manifeste(nom) is None:
            return _H["passe"]
        return fn(k, t)
    garde.__name__ = f"skill_{nom}"
    return garde


def enregistrer(skill, passe, liste=None):
    """Appele par kitt_complet au demarrage. `skill` est son decorateur, `passe` son sentinelle,
    `liste` la liste SKILLS (pour retirer ou remplacer une recette)."""
    _H["skill"] = skill
    _H["passe"] = passe
    _H["liste"] = liste
    for nom, decl, fn in COMMANDES:
        skill(nom, decl)(fn)
    for nom, info in CATALOGUE.items():
        skill(nom, info["declencheurs"])(_protege(nom, _FONCTIONS[nom]))
    # Applications : en dernier, pour que les jeux et les autres skills gardent la priorite.
    skill("app_ajouter", ["ajoute l'application", "ajoute l application"])(cmd_ajouter_app)
    skill("app_ouvrir", ["ouvre", "ouvrir", "lance", "lancer", "demarre", "demarrer"])(cmd_ouvrir_app)
    _recettes_existantes()
