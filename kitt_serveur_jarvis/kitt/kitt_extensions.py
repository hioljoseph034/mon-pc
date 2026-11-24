"""Modules « Jarvis » ajoutés à KITT.

Ils s'insèrent en tête de liste des modules : ce sont eux qui répondent quand un mot-clé correspond.
Pilotage uniquement par mots-clés : aucun modèle en ligne ne décide à la place de KITT. Les services
externes ne sont appelés que pour la demande précise de l'utilisateur, et seulement si leur clé
est présente dans le fichier .env.

Clés lues dans .env (toutes facultatives, chaque module indique celle qui manque) :
  GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN  -> e-mails, boîte mail, Google Docs
  BREVO_API_KEY, BREVO_SENDER                                -> e-mails (si pas de Gmail)
  INFOBIP_BASE_URL, INFOBIP_API_KEY, INFOBIP_SENDER          -> SMS
  TAVILY_API_KEY                                             -> recherche web
  CF_ACCOUNT_ID, CF_API_TOKEN, CF_IMAGE_MODEL                -> images
  TIMEZONE                                                   -> fuseau (par défaut Africa/Douala)
"""

import base64
import json
import os
import re
import tempfile
import time
from datetime import datetime, timedelta
from email import policy as email_policy
from email import message_from_bytes
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import httpx

# Fonction d'envoi de fichier vers Telegram, fournie par kitt_telegram au démarrage
ENVOYER_FICHIER = None

WMO = {0: "ciel dégagé", 1: "plutôt dégagé", 2: "partiellement nuageux", 3: "couvert",
       45: "brouillard", 48: "brouillard givrant", 51: "bruine légère", 53: "bruine",
       55: "bruine forte", 61: "pluie faible", 63: "pluie modérée", 65: "pluie forte",
       71: "neige faible", 73: "neige", 75: "forte neige", 80: "averses légères",
       81: "averses", 82: "fortes averses", 95: "orage", 96: "orage avec grêle",
       99: "orage violent avec grêle"}

PASSE_ICI = None  # renseigné dans enregistrer()
_GENERER = None   # fonction de génération du modèle local, fournie par kitt_complet

INTENTIONS_PROMPT = """Tu classes la demande de l'utilisateur dans une action. Réponds UNIQUEMENT par un objet JSON
sur une seule ligne, sans aucun texte autour.
Actions possibles :
- {"action":"meteo","ville":"..."}
- {"action":"recherche","requete":"..."}   (informations récentes, actualités, recherche sur internet)
- {"action":"image","description":"..."}   (dessiner, illustrer, créer une image)
- {"action":"sms","numero":"indicatif et numéro sans +","texte":"..."}
- {"action":"mail","destinataire":"adresse","objet":"...","corps":"..."}
- {"action":"mails_non_lus"}
- {"action":"mail_de","expediteur":"..."}
- {"action":"doc_creer","titre":"...","contenu":"..."}   (contenu peut être vide)
- {"action":"doc_lire","titre":"..."}
- {"action":"doc_ajouter","titre":"...","texte":"..."}
- {"action":"serveur_etat"}   (état du serveur, mémoire, disque, santé du système)
- {"action":"identite"}   (qui es-tu, d'où viens-tu, présente-toi)
- {"action":"aucune"}   (simple discussion, question générale, ou action non listée)
N'invente jamais une adresse, un numéro ou un titre : si une information manque, mets une chaîne vide."""


def _env(nom, defaut=""):
    return os.environ.get(nom, defaut).strip()


def _maintenant():
    try:
        return datetime.now(ZoneInfo(_env("TIMEZONE", "Africa/Douala")))
    except Exception:
        return datetime.now()


def _erreur(e):
    """Message clair pour l'utilisateur ; le détail reste dans la console."""
    print(f"[module Jarvis] {e}", flush=True)
    raw = str(e).lower()
    if "429" in raw or "quota" in raw or "rate" in raw:
        return "Je suis à court de capacité pour le moment. Réessayez dans une minute."
    if "timeout" in raw or "timed out" in raw:
        return "Ça prend plus de temps que prévu. Réessayez dans un instant."
    if "connect" in raw or "unreachable" in raw or "network" in raw:
        return "Je n'arrive pas à joindre ce service pour le moment."
    if "401" in raw or "403" in raw or "non configuré" in raw or "manquant" in raw:
        return "Je n'ai pas l'accès nécessaire à ce service. Sa configuration est à vérifier."
    if "404" in raw or "not found" in raw:
        return "Ce service a changé de fonctionnement, je ne peux pas le faire pour l'instant."
    return "Quelque chose n'a pas fonctionné de mon côté."


# ----------------------------------------------------------------------------
# Google (Gmail, Docs, Drive)
# ----------------------------------------------------------------------------
_JETON = {}


def _google_token():
    if _JETON.get("exp", 0) > datetime.now().timestamp() + 60:
        return _JETON["tok"]
    refresh = _env("GMAIL_REFRESH_TOKEN")
    if not refresh:
        raise RuntimeError("Google non configuré (GMAIL_REFRESH_TOKEN manquant)")
    r = httpx.post("https://oauth2.googleapis.com/token", data={
        "client_id": _env("GMAIL_CLIENT_ID"), "client_secret": _env("GMAIL_CLIENT_SECRET"),
        "refresh_token": refresh, "grant_type": "refresh_token"}, timeout=20).json()
    if "access_token" not in r:
        raise RuntimeError(f"Autorisation Google refusée : {r.get('error')}")
    _JETON["tok"] = r["access_token"]
    _JETON["exp"] = datetime.now().timestamp() + int(r.get("expires_in", 3600))
    return _JETON["tok"]


def _g(method, url, **kw):
    r = httpx.request(method, url, headers={"Authorization": f"Bearer {_google_token()}"}, timeout=30, **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"Google ({r.status_code}) : {r.text[:150]}")
    return r.json()


def _envoyer_mail(destinataire, sujet, corps):
    if _env("GMAIL_REFRESH_TOKEN"):
        msg = EmailMessage()
        msg["To"], msg["Subject"] = destinataire, sujet
        msg.set_content(corps)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        _g("POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/send", json={"raw": raw})
        return
    if _env("BREVO_API_KEY"):
        r = httpx.post("https://api.brevo.com/v3/smtp/email", headers={
            "api-key": _env("BREVO_API_KEY"), "accept": "application/json"}, json={
            "sender": {"email": _env("BREVO_SENDER"), "name": "KITT"},
            "to": [{"email": destinataire}], "subject": sujet, "textContent": corps}, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"Brevo ({r.status_code}) : {r.text[:150]}")
        return
    raise RuntimeError("Envoi d'e-mails non configuré (GMAIL_REFRESH_TOKEN manquant)")


def _envoyer_sms(numero, texte):
    base = _env("INFOBIP_BASE_URL").replace("https://", "").replace("http://", "").strip("/")
    cle = _env("INFOBIP_API_KEY")
    if not base or not cle:
        raise RuntimeError("Envoi de SMS non configuré (INFOBIP_API_KEY manquant)")
    r = httpx.post(f"https://{base}/sms/2/text/advanced", headers={
        "Authorization": f"App {cle}", "Content-Type": "application/json", "Accept": "application/json"},
        json={"messages": [{"from": _env("INFOBIP_SENDER", "KITT"),
                            "destinations": [{"to": numero}], "text": texte}]}, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"Infobip ({r.status_code}) : {r.text[:150]}")


def _entetes(msg):
    return {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}


def _texte_mail(payload):
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        raw = payload["body"]["data"]
        return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8", errors="ignore")
    for part in payload.get("parts", []) or []:
        t = _texte_mail(part)
        if t:
            return t
    return ""


# ----------------------------------------------------------------------------
# Extraction simple dans la phrase
# ----------------------------------------------------------------------------
def _apres_deux_points(t):
    return t.split(":", 1)[1].strip() if ":" in t else ""


def _apres(t, *mots):
    for m in mots:
        p = re.search(r"\b" + re.escape(m) + r"\b\s*(.+)$", t, re.IGNORECASE)
        if p:
            return p.group(1).strip(" :,.")
    return ""


# ----------------------------------------------------------------------------
# Modules
# ----------------------------------------------------------------------------
def m_meteo(k, t):
    ville = _apres(t, "à", "a", "de", "pour") or "Douala"
    try:
        with httpx.Client(timeout=15) as http:
            geo = http.get("https://geocoding-api.open-meteo.com/v1/search",
                           params={"name": ville, "count": 1, "language": "fr"}).json()
            if not geo.get("results"):
                return f"Je ne trouve pas la ville {ville}. Pouvez-vous la préciser ?"
            loc = geo["results"][0]
            w = http.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": loc["latitude"], "longitude": loc["longitude"],
                "current": "temperature_2m,apparent_temperature,wind_speed_10m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min", "timezone": "auto",
                "forecast_days": 2}).json()
    except Exception as e:
        return _erreur(e)
    c, d = w["current"], w["daily"]
    return (f"À {loc['name']}, il fait {round(c['temperature_2m'])} °C, "
            f"{WMO.get(c['weather_code'], 'temps variable')}, avec un ressenti de "
            f"{round(c['apparent_temperature'])} °C. Demain, entre {round(d['temperature_2m_min'][1])} "
            f"et {round(d['temperature_2m_max'][1])} °C.")


def m_recherche_web(k, t):
    if not _env("TAVILY_API_KEY"):
        return "La recherche web n'est pas configurée pour le moment."
    requete = re.sub(r"(?i)recherche sur internet|cherche sur internet|cherche sur le web|dernières nouvelles|actualités", "", t).strip(" :,.")
    try:
        r = httpx.post("https://api.tavily.com/search", json={
            "api_key": _env("TAVILY_API_KEY"), "query": requete or t, "max_results": 3,
            "include_answer": True}, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"Tavily ({r.status_code}) : {r.text[:150]}")
        data = r.json()
    except Exception as e:
        return _erreur(e)
    reponse = data.get("answer") or "Je n'ai rien trouvé de clair."
    sources = [x.get("url", "") for x in data.get("results", [])[:2] if x.get("url")]
    return reponse + ((" Sources : " + ", ".join(sources)) if sources else "")


def m_image(k, t):
    if not ENVOYER_FICHIER:
        return "L'envoi d'images n'est pas disponible dans cette configuration."
    if not _env("CF_ACCOUNT_ID") or not _env("CF_API_TOKEN"):
        return "La génération d'images n'est pas configurée pour le moment."
    description = re.split(r"(?i)dessine(?:-moi)?|génère une image|genere une image|crée une image|cree une image", t, 1)[-1]
    description = description.strip(" :,.")
    if not description:
        return "Que dois-je dessiner ?"
    modele = _env("CF_IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell")
    try:
        r = httpx.post(f"https://api.cloudflare.com/client/v4/accounts/{_env('CF_ACCOUNT_ID')}/ai/run/{modele}",
                       headers={"Authorization": f"Bearer {_env('CF_API_TOKEN')}"},
                       json={"prompt": description, "steps": 4}, timeout=120)
        if r.status_code >= 400:
            raise RuntimeError(f"Cloudflare ({r.status_code}) : {r.text[:150]}")
        if r.headers.get("content-type", "").startswith("image/"):
            octets = r.content
        else:
            octets = base64.b64decode(r.json()["result"]["image"])
        chemin = os.path.join(tempfile.gettempdir(), "kitt_image.png")
        with open(chemin, "wb") as f:
            f.write(octets)
        ENVOYER_FICHIER(chemin, "image.png")
    except Exception as e:
        return _erreur(e)
    return "Voici l'image."


def m_sms(k, t):
    trouve = re.search(r"\+?\d[\d ]{7,}\d", t)
    if not trouve:
        return "À quel numéro dois-je envoyer le SMS ? Indiquez-le avec l'indicatif du pays."
    numero = re.sub(r"\D", "", trouve.group())
    texte = _apres_deux_points(t) or _apres(t, "dire que", "pour dire que")
    if not texte:
        return "Que dois-je écrire dans le SMS ? Dites-le après deux-points."
    if not k.confirmer(f"J'envoie ce SMS au {numero} : « {texte[:160]} ». Je l'envoie ?"):
        return "D'accord, je n'envoie pas ce SMS."
    try:
        _envoyer_sms(numero, texte[:480])
    except Exception as e:
        return _erreur(e)
    return "C'est envoyé."


def m_mail(k, t):
    adresse = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", t)
    if not adresse:
        return "À quelle adresse dois-je écrire ?"
    corps = _apres_deux_points(t)
    if not corps:
        return "Que dois-je dire dans ce mail ? Dites-le après deux-points."
    objet = _apres(t.split(":", 1)[0], "objet") or "Message"
    if not k.confirmer(f"J'envoie ce mail à {adresse.group()}, objet « {objet} », avec le texte : {corps[:300]}. Je l'envoie ?"):
        return "D'accord, je n'envoie pas ce mail."
    try:
        _envoyer_mail(adresse.group(), objet, corps)
    except Exception as e:
        return _erreur(e)
    return "Le mail est parti."


def m_mails_lire(k, t):
    n = re.search(r"lis le (?:mail|e-?mail) de (.+)$", t, re.IGNORECASE)
    try:
        if n:
            expediteur = n.group(1).strip(" .,")
            liste = _g("GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                       params={"q": f"from:{expediteur}", "maxResults": 1}).get("messages", [])
            if not liste:
                return f"Je ne trouve pas de mail de {expediteur}."
            msg = _g("GET", f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{liste[0]['id']}",
                     params={"format": "full"})
            h = _entetes(msg)
            corps = (_texte_mail(msg.get("payload", {})) or msg.get("snippet", ""))[:1200]
            return f"Mail de {h.get('from', '')}, objet « {h.get('subject', '')} ». {corps}"
        liste = _g("GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                   params={"q": "is:unread", "maxResults": 5}).get("messages", [])
        if not liste:
            return "Vous n'avez aucun mail non lu."
        lignes = []
        for i, m in enumerate(liste, 1):
            msg = _g("GET", f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{m['id']}",
                     params=[("format", "metadata"), ("metadataHeaders", "From"), ("metadataHeaders", "Subject")])
            h = _entetes(msg)
            lignes.append(f"{i}. de {h.get('from', '?')} : {h.get('subject', '(sans objet)')}")
        return "Vos mails non lus : " + " ; ".join(lignes) + "."
    except Exception as e:
        return _erreur(e)


def m_docs(k, t):
    try:
        bas = t.lower()
        if re.search(r"(crée|cree|fais|ouvre un nouveau|nouveau) .*document", bas):
            titre = _apres(t.split(":", 1)[0], "intitulé", "intitule", "nommé", "nomme", "appelé", "appele") or "Sans titre"
            contenu = _apres_deux_points(t)
            doc = _g("POST", "https://docs.googleapis.com/v1/documents", json={"title": titre[:200]})
            if contenu:
                _g("POST", f"https://docs.googleapis.com/v1/documents/{doc['documentId']}:batchUpdate",
                   json={"requests": [{"insertText": {"location": {"index": 1}, "text": contenu}}]})
            return f"J'ai créé le document « {titre} ». Lien : https://docs.google.com/document/d/{doc['documentId']}/edit"
        n = re.search(r"(?:document|doc)\s+(?:google\s+)?(?:intitulé\s+|intitule\s+|appelé\s+|appele\s+|nommé\s+|nomme\s+)?(.+?)(?:\s*:|$)", t, re.IGNORECASE)
        if not n:
            return "Quel document ? Donnez-moi son titre."
        nom = n.group(1).strip(" .,")
        fichiers = _g("GET", "https://www.googleapis.com/drive/v3/files", params={
            "q": f"mimeType='application/vnd.google-apps.document' and trashed=false and name contains '{nom.replace(chr(39), '')}'",
            "pageSize": 5, "fields": "files(id,name,webViewLink)"}).get("files", [])
        if not fichiers:
            return f"Je ne trouve aucun document appelé « {nom} »."
        f = fichiers[0]
        ajout = _apres_deux_points(t)
        if ajout:
            _g("POST", f"https://docs.googleapis.com/v1/documents/{f['id']}:batchUpdate", json={"requests": [
                {"insertText": {"endOfSegmentLocation": {"segmentId": ""}, "text": "\n" + ajout}}]})
            return f"J'ai ajouté le texte à « {f['name']} »."
        doc = _g("GET", f"https://docs.googleapis.com/v1/documents/{f['id']}")
        texte = "".join(pe.get("textRun", {}).get("content", "") for el in doc.get("body", {}).get("content", [])
                        for pe in el.get("paragraph", {}).get("elements", []))
        return f"« {f['name']} » : {texte[:1200].strip() or 'ce document est vide.'} Lien : {f.get('webViewLink', '')}"
    except Exception as e:
        return _erreur(e)


# ----------------------------------------------------------------------------
# État du serveur (lecture seule : on mesure, on n'agit jamais sur la machine)
# ----------------------------------------------------------------------------
SEUIL_MEMOIRE = 90      # %
SEUIL_DISQUE = 90       # %
SEUIL_CHARGE = 2.0      # charge par cœur
DELAI_RAPPEL_ALERTE = 7200   # secondes avant de resignaler un problème qui persiste
INTERVALLE_CONTROLE = 300    # secondes entre deux contrôles automatiques
_ALERTES = {}                # clé du problème -> date du dernier message
_DERNIER_CONTROLE = [0.0]


def _lire_fichier(chemin):
    try:
        with open(chemin, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _memoire():
    infos = {}
    for ligne in _lire_fichier("/proc/meminfo").splitlines():
        cle, _, valeur = ligne.partition(":")
        infos[cle.strip()] = int(valeur.strip().split()[0]) if valeur.strip() else 0
    total = infos.get("MemTotal", 0)
    dispo = infos.get("MemAvailable", 0)
    if not total:
        return None
    return {"total_go": total / 1048576, "utilisee_go": (total - dispo) / 1048576,
            "pct": round(100 * (total - dispo) / total)}


def _disque():
    try:
        st = os.statvfs(os.path.expanduser("~"))
    except OSError:
        return None
    total = st.f_blocks * st.f_frsize
    libre = st.f_bavail * st.f_frsize
    if not total:
        return None
    return {"total_go": total / 1e9, "pct": round(100 * (total - libre) / total)}


def _uptime_texte():
    try:
        secondes = float(_lire_fichier("/proc/uptime").split()[0])
    except (ValueError, IndexError):
        return "durée inconnue"
    jours, reste = divmod(int(secondes), 86400)
    heures, minutes = divmod(reste // 60, 60)
    if jours:
        return f"{jours} jour(s) et {heures} h"
    return f"{heures} h {minutes} min"


def _ollama_ok():
    try:
        return httpx.get("http://127.0.0.1:11434/api/version", timeout=3).status_code == 200
    except Exception:
        return False


def _problemes():
    """Liste (clé, message) des problèmes actuels. Vide si tout va bien."""
    problemes = []
    mem = _memoire()
    if mem and mem["pct"] >= SEUIL_MEMOIRE:
        problemes.append(("memoire", f"la mémoire est presque pleine ({mem['pct']} % utilisés)"))
    disque = _disque()
    if disque and disque["pct"] >= SEUIL_DISQUE:
        problemes.append(("disque", f"le disque est presque plein ({disque['pct']} % occupés)"))
    try:
        charge = os.getloadavg()[0] / (os.cpu_count() or 1)
        if charge >= SEUIL_CHARGE:
            problemes.append(("charge", "le serveur est très sollicité en ce moment"))
    except OSError:
        pass
    if not _ollama_ok():
        problemes.append(("ollama", "le modèle local (Ollama) ne répond plus"))
    return problemes


def m_serveur_etat(k, t):
    mem, disque = _memoire(), _disque()
    morceaux = [f"Le serveur tourne depuis {_uptime_texte()}."]
    if mem:
        morceaux.append(f"Mémoire : {mem['utilisee_go']:.1f} Go utilisés sur {mem['total_go']:.1f} Go "
                        f"({mem['pct']} %).")
    if disque:
        morceaux.append(f"Disque : {disque['pct']} % occupé.")
    morceaux.append("Le modèle local répond." if _ollama_ok() else "Attention, le modèle local ne répond pas.")
    problemes = _problemes()
    if problemes:
        morceaux.append("Points à surveiller : " + " ; ".join(m for _c, m in problemes) + ".")
    else:
        morceaux.append("Tout va bien de ce côté-là.")
    return " ".join(morceaux)


def verifier_serveur(envoyer):
    """Appelé régulièrement par la tâche de fond : signale un problème une fois, puis le confirme
    quand il disparaît. Un problème qui persiste n'est resignalé qu'après DELAI_RAPPEL_ALERTE."""
    maintenant = time.time()
    if maintenant - _DERNIER_CONTROLE[0] < INTERVALLE_CONTROLE:
        return
    _DERNIER_CONTROLE[0] = maintenant
    actuels = {cle: msg for cle, msg in _problemes()}
    for cle, msg in actuels.items():
        dernier = _ALERTES.get(cle)
        if dernier is None or maintenant - dernier >= DELAI_RAPPEL_ALERTE:
            _ALERTES[cle] = maintenant
            try:
                envoyer(f"⚠️ Petit souci sur le serveur : {msg}. Je surveille et je vous préviens dès que ça revient à la normale.")
            except Exception as e:
                print(f"[alerte non envoyée : {e}]", flush=True)
    for cle in list(_ALERTES):
        if cle not in actuels:
            del _ALERTES[cle]
            try:
                envoyer("✅ Bonne nouvelle : le serveur est revenu à la normale.")
            except Exception as e:
                print(f"[message non envoyé : {e}]", flush=True)


# ----------------------------------------------------------------------------
# Identité de KITT
# ----------------------------------------------------------------------------
def identite_texte():
    """Présentation de KITT. Le créateur se règle avec KITT_CREATEUR dans le .env."""
    createur = _env("KITT_CREATEUR")
    origine = (f"Je suis né d'un projet imaginé par {createur}" if createur
               else "Je suis né d'un projet personnel, sur un serveur quelque part")
    return (f"Je suis KITT. {origine}, inspiré de la voiture parlante de la série K2000 : "
            "loyal, un peu malicieux, et toujours prêt à rendre service. "
            "Mon rôle : gérer votre quotidien, vos messages, vos recherches et vos rendez-vous, "
            "en gardant le volant entre vos mains. Je réfléchis avec un modèle installé sur ce serveur, "
            "et je ne fais appel à des services extérieurs que lorsque vous me le demandez. "
            "Pour le reste, posez-moi la question : je ne mords que les bugs.")


def m_identite(k, t):
    return identite_texte()


# (nom, mots-clés, fonction) : l'ordre compte, le premier qui correspond répond
MODULES = [
    ("identite", ["qui es tu", "qui es-tu", "presente toi", "presente-toi", "d ou viens tu",
                  "d'ou viens tu", "tu viens d ou", "tu viens d'ou", "ton histoire", "qui t as cree",
                  "qui t'a cree", "qui es tu vraiment"], m_identite),
    ("serveur_etat", ["etat du serveur", "etat serveur", "situation du serveur", "comment va le serveur",
                      "resume du serveur", "etat du systeme", "sante du serveur"], m_serveur_etat),
    ("jarvis_meteo", ["meteo", "quel temps", "temps fait"], m_meteo),
    ("jarvis_web", ["recherche sur internet", "cherche sur internet", "cherche sur le web",
                    "dernieres nouvelles", "actualites"], m_recherche_web),
    ("jarvis_image", ["dessine", "genere une image", "cree une image"], m_image),
    ("jarvis_sms", ["envoie un sms", "sms a "], m_sms),
    ("jarvis_mail_envoi", ["envoie un mail a", "envoie un e-mail a", "envoie un email a",
                           "ecris un mail a", "ecris un e-mail a", "ecris un email a"], m_mail),
    ("jarvis_mails_lire", ["mes mails", "mes e-mails", "mes emails", "boite mail",
                           "lis le mail de", "lis le e-mail de", "lis le email de"], m_mails_lire),
    ("jarvis_docs", ["document google", "google docs", "doc google", "mon document"], m_docs),
]


def tenter_intention(k, texte):
    """Compréhension libre : le modèle local choisit l'action, le module Jarvis l'exécute.
    Renvoie False si rien ne correspond, pour laisser la main à la discussion."""
    if _GENERER is None:
        return False
    try:
        brut = _GENERER(INTENTIONS_PROMPT, f"Demande : {texte}\nJSON :", max_tokens=160,
                        delai=60, temperature=0.0)
    except Exception as e:
        print(f"[compréhension indisponible : {e}]", flush=True)
        return False
    trouve = re.search(r"\{.*\}", brut or "", re.S)
    if not trouve:
        return False
    try:
        d = json.loads(trouve.group())
    except json.JSONDecodeError:
        return False
    a = d.get("action", "aucune")
    rep = None
    if a == "meteo":
        rep = m_meteo(k, f"météo à {d.get('ville', '')}")
    elif a == "recherche":
        rep = m_recherche_web(k, str(d.get("requete", "")))
    elif a == "image":
        rep = m_image(k, "dessine " + str(d.get("description", "")))
    elif a == "sms":
        rep = m_sms(k, f"envoie un sms au {d.get('numero', '')} : {d.get('texte', '')}")
    elif a == "mail":
        rep = m_mail(k, f"envoie un mail à {d.get('destinataire', '')} objet {d.get('objet', '')} : {d.get('corps', '')}")
    elif a == "mails_non_lus":
        rep = m_mails_lire(k, "mes mails non lus")
    elif a == "mail_de":
        rep = m_mails_lire(k, f"lis le mail de {d.get('expediteur', '')}")
    elif a == "identite":
        rep = m_identite(k, "")
    elif a == "serveur_etat":
        rep = m_serveur_etat(k, "")
    elif a == "doc_creer":
        rep = m_docs(k, f"crée un document intitulé {d.get('titre', '')} : {d.get('contenu', '')}")
    elif a == "doc_lire":
        rep = m_docs(k, f"ouvre le document {d.get('titre', '')}")
    elif a == "doc_ajouter":
        rep = m_docs(k, f"ajoute au document {d.get('titre', '')} : {d.get('texte', '')}")
    if not rep:
        return False
    k.parler(rep)
    return True


def enregistrer(skill, passe, liste, generer=None):
    """Appelé par kitt_complet au démarrage. Les modules sont placés en tête de liste."""
    global PASSE_ICI, _GENERER
    PASSE_ICI = passe
    _GENERER = generer
    avant = len(liste)
    for nom, declencheurs, fn in MODULES:
        skill(nom, declencheurs)(fn)
    nouveaux = liste[avant:]
    del liste[avant:]
    liste[:0] = nouveaux  # priorité aux modules Jarvis (remplace l'e-mail local de KITT)
    print(f"[modules Jarvis chargés : {len(MODULES)}]", flush=True)
