"""Initiatives de KITT : il prend la parole de lui-meme quand c'est utile.

Ce qu'il fait seul : signaler une situation (pause apres une longue session, batterie faible,
heure tardive, disque presque plein, taches en attente).
Ce qu'il ne fait JAMAIS seul : envoyer un message, passer un appel, fermer un programme,
activer Internet ou modifier un fichier. Ces actions restent sur votre demande, avec confirmation.

Garde-fous : une seule initiative a la fois, seulement quand KITT est libre de parler,
un delai minimum avant de repeter la meme annonce, et chaque annonce est inscrite dans le journal.
Desactivable : « desactive les initiatives ».
"""
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import kitt_ton as ton
import kitt_idees

try:
    import psutil
except ImportError:
    psutil = None

PAUSE_INACTIVITE = timedelta(minutes=30)     # au-dela, une nouvelle session commence
DELAI_CONTEXTE = timedelta(seconds=60)       # on relit batterie et disque au plus une fois par minute
MIN_SESSIONS = 5                             # en dessous, KITT n'apprend rien et garde ses reglages
SESSION_MIN = 5                              # une session plus courte que 5 minutes ne compte pas


def contexte(mem, dossier=None):
    """Faits utiles pour decider. Chaque source peut manquer sans bloquer KITT."""
    ctx = {}
    try:
        batterie = psutil.sensors_battery() if psutil else None
        if batterie is not None:
            ctx["batterie"] = (round(batterie.percent), bool(batterie.power_plugged))
    except Exception:
        pass
    try:
        u = shutil.disk_usage(dossier or Path.home())
        ctx["disque_libre_pct"] = 100 * u.free / u.total
    except OSError:
        pass
    try:
        ctx["taches"] = mem.exe("SELECT COUNT(*) FROM taches WHERE fait = 0")[0][0]
    except Exception:
        pass
    return ctx


def _assurer_table(mem):
    mem.exe("CREATE TABLE IF NOT EXISTS sessions(debut TEXT PRIMARY KEY, fin TEXT)")


def _mediane(valeurs):
    v = sorted(valeurs)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def apprendre(mem):
    """Profil appris a partir des sessions passees (table sessions de kitt.db).

    - pause_min : 75e centile de la duree des sessions, borne entre 45 et 180 minutes ;
    - coucher   : heure (decimale) ou vous arretez habituellement, borne entre 21 h et 24 h.
    Sans assez de donnees, la valeur reste None et KITT garde ses reglages."""
    _assurer_table(mem)
    durees, fins = [], []
    for debut, fin in mem.exe("SELECT debut, fin FROM sessions ORDER BY debut DESC LIMIT 60"):
        try:
            d, f = datetime.fromisoformat(debut), datetime.fromisoformat(fin)
        except (TypeError, ValueError):
            continue
        duree = (f - d).total_seconds() / 60
        if duree < SESSION_MIN:
            continue
        durees.append(duree)
        heure = f.hour + f.minute / 60
        if 20 <= heure <= 24:
            fins.append(heure)
    profil = {"pause_min": None, "coucher": None, "sessions": len(durees)}
    if len(durees) >= MIN_SESSIONS:
        durees.sort()
        q75 = durees[int(0.75 * (len(durees) - 1))]
        profil["pause_min"] = int(min(max(q75, 45), 180))
    if len(fins) >= MIN_SESSIONS:
        profil["coucher"] = min(max(_mediane(fins) + 0.5, 21.0), 24.0)
    return profil


def resume(profil):
    """Phrase lisible pour « mes habitudes »."""
    if profil["sessions"] < MIN_SESSIONS:
        return (f"Je dois encore observer quelques sessions avant de connaître vos habitudes "
                f"({profil['sessions']} enregistrée(s) pour l'instant).")
    morceaux = []
    if profil["pause_min"]:
        morceaux.append(f"vos sessions durent en général jusqu'à {profil['pause_min']} minutes, "
                        "je vous signale une pause au-delà")
    if profil["coucher"]:
        h = int(profil["coucher"])
        m = int(round((profil["coucher"] - h) * 60))
        morceaux.append(f"vous arrêtez souvent vers {h} h {m:02d}, je vous le rappellerai à ce moment-là")
    return "D'après vos habitudes : " + " ; ".join(morceaux) + "." if morceaux else \
        "Je n'ai pas encore assez de sessions pour dégager une habitude."


class Initiatives:
    def __init__(self):
        self.debut_session = None
        self.derniere_activite = None
        self.dernieres_annonces = {}          # cle -> moment de la derniere annonce
        self.prochain_contexte = datetime.min
        self.ctx = {}
        self.profil = {"pause_min": None, "coucher": None, "sessions": 0}

    def activite(self, now, mem=None):
        """A appeler a chaque commande de l'utilisateur. Avec `mem`, la session est enregistree."""
        nouvelle = self.derniere_activite is None or now - self.derniere_activite > PAUSE_INACTIVITE
        if nouvelle:
            self.debut_session = now
            self.dernieres_annonces.pop("pause", None)   # nouvelle session : pause de nouveau possible
        self.derniere_activite = now
        if mem is not None and self.debut_session:
            _assurer_table(mem)
            horodatage = self.debut_session.isoformat(timespec="seconds")
            if nouvelle:
                mem.exe("INSERT OR IGNORE INTO sessions VALUES (?,?)",
                        (horodatage, now.isoformat(timespec="seconds")))
            else:
                mem.exe("UPDATE sessions SET fin = ? WHERE debut = ?",
                        (now.isoformat(timespec="seconds"), horodatage))

    def pause_effective(self, pause_config, auto=True):
        """Pause appliquee : la valeur apprise si elle existe et si l'apprentissage est actif."""
        if auto and self.profil.get("pause_min"):
            return self.profil["pause_min"]
        return pause_config

    def coucher_effectif(self):
        return self.profil.get("coucher")

    def _peut(self, cle, now, delai):
        d = self.dernieres_annonces.get(cle)
        return d is None or now - d >= delai

    def decider(self, now, ctx, prenom, pause_minutes=90, coucher=None, idees=False):
        """Renvoie la liste des (cle, message) a dire maintenant, les plus urgentes d'abord.
        Ne parle pas, ne touche a rien."""
        out = []
        pause = timedelta(minutes=pause_minutes)

        batterie = ctx.get("batterie")
        if batterie and batterie[0] <= 15 and not batterie[1] \
                and self._peut("batterie", now, timedelta(minutes=30)):
            out.append(("batterie", ton.phrase("batterie", niveau=str(batterie[0]), prenom=prenom)))

        recent = self.derniere_activite and now - self.derniere_activite < timedelta(minutes=5)
        heure = now.hour + now.minute / 60
        seuil = coucher if coucher else 23.0
        if (heure >= seuil or heure < 5) and recent and self._peut("tard", now, timedelta(hours=6)):
            out.append(("tard", ton.phrase("tard", heure=f"{now:%H:%M}", prenom=prenom)))

        libre = ctx.get("disque_libre_pct")
        if libre is not None and libre < 5 and self._peut("disque", now, timedelta(hours=24)):
            out.append(("disque", ton.phrase("disque", libre=f"{libre:.0f}")))

        taches = ctx.get("taches", 0)
        if taches >= 5 and ton.moment(now.hour) in ("matin", "apresmidi") \
                and self._peut("taches", now, timedelta(hours=24)):
            out.append(("taches", ton.phrase("taches", nombre=str(taches), prenom=prenom)))
        # Une idee, rarement, seulement si rien d'autre n'est a signaler et si l'option est active.
        if idees and not out and self._peut("idee", now, timedelta(hours=24)) and \
                self.derniere_activite and now - self.derniere_activite < timedelta(minutes=5):
            out.append(("idee", kitt_idees.idee_spontanee(ctx, prenom)))
        # La pause vient en dernier : c'est la moins urgente des initiatives.
        if self.debut_session and now - self.debut_session >= pause and self._peut("pause", now, pause):
            minutes = int((now - self.debut_session).total_seconds() // 60)
            out.append(("pause", ton.phrase("pause", minutes=str(minutes), prenom=prenom)))
        return out

    def annoncer(self, cle, now):
        self.dernieres_annonces[cle] = now

    def contexte_a_jour(self, now, mem):
        if now >= self.prochain_contexte:
            self.ctx = contexte(mem)
            self.profil = apprendre(mem)
            self.prochain_contexte = now + DELAI_CONTEXTE
        return self.ctx
