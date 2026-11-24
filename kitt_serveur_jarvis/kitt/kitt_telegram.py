"""KITT en ligne : le cœur de KITT (mémoire, agenda, tâches, rédaction, calculs, discussion locale
via Ollama) relié à un bot Telegram réservé à un seul utilisateur.

Lancement :  python kitt_telegram.py

Configuration (fichier .env ou variables d'environnement) :
  TELEGRAM_TOKEN       token donné par BotFather
  TELEGRAM_OWNER_ID    votre identifiant Telegram numérique (obtenu avec @userinfobot).
                       Tout autre expéditeur est ignoré sans réponse.

Ce qui est retiré : tout ce qui agit sur la machine (applications, fermeture de programmes, fichiers
locaux, état du système), les gestes, les jeux, les échecs, YouTube, les appels et WhatsApp.

Ajouts : messages vocaux Telegram transcrits (Vosk + ffmpeg), réponses vocales (espeak-ng, « active la voix »),
labo 3D envoyé en fichier HTML, et « envoie la sauvegarde » qui renvoie la base en zip.
"""
import asyncio
import json
import os
import queue
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

import kitt_complet as kc
import kitt_extensions as kx
import kitt_idees
import kitt_labo3d as kl3
import kitt_recherche as kr
import kitt_skills
import kitt_securite as sec
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
try:
    PROPRIETAIRE = int(os.environ.get("TELEGRAM_OWNER_ID", "0").strip())
except ValueError:
    PROPRIETAIRE = 0

# Modules qui agissent sur la machine ou dépendent d'un écran, de la voix ou du navigateur.
MODULES_RETIRES = {
    "ouvrir", "fermer", "diagnostic", "sauvegarde", "situation",
    "fichier_resumer", "fichier_lire", "fichier_question", "fichier_joint",
    "jeux", "echecs", "youtube", "appel", "whatsapp", "app_ajouter", "app_ouvrir",
}
LONGUEUR_MESSAGE = 3900          # limite Telegram : 4096 caractères


def voix_disponible():
    return shutil.which("espeak-ng") is not None and shutil.which("ffmpeg") is not None


def _couper_phrase(texte, limite=700):
    """Pour la voix : on lit les premières phrases, pas un long document."""
    texte = kc.vers_parole(texte).strip()
    if len(texte) <= limite:
        return texte
    coupe = max(texte.rfind(". ", 0, limite), texte.rfind(", ", 0, limite))
    return texte[:coupe + 1] if coupe > 100 else texte[:limite]


def dire_voix(texte):
    """Synthèse hors ligne (espeak-ng, voix française) puis message vocal Telegram (OGG Opus)."""
    if not voix_disponible():
        raise RuntimeError("espeak-ng ou ffmpeg absent")
    dossier = Path(tempfile.mkdtemp(prefix="kitt-voix-"))
    try:
        wav, ogg = dossier / "voix.wav", dossier / "voix.ogg"
        subprocess.run(["espeak-ng", "-v", "fr", "-s", "165", "-w", str(wav)],
                       input=_couper_phrase(texte).encode("utf-8"), check=True, timeout=60)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "libopus",
                        "-b:a", "32k", str(ogg)], check=True, timeout=60)
        with ogg.open("rb") as f:
            futur = asyncio.run_coroutine_threadsafe(
                BOT.send_voice(chat_id=PROPRIETAIRE, voice=f), BOUCLE)
            futur.result(timeout=120)
    finally:
        shutil.rmtree(dossier, ignore_errors=True)


def envoyer_document(chemin, nom):
    """Envoie un fichier au propriétaire (depuis le thread de KITT)."""
    with Path(chemin).open("rb") as f:
        futur = asyncio.run_coroutine_threadsafe(
            BOT.send_document(chat_id=PROPRIETAIRE, document=f, filename=nom), BOUCLE)
        futur.result(timeout=300)


kx.ENVOYER_FICHIER = envoyer_document


class KittServeur(kc.Kitt):
    """Kitt sans écran ni voix : les réponses partent vers Telegram via `envoyer`."""

    def __init__(self, envoyer):
        super().__init__(ui=None)
        self._envoyer = envoyer
        self.voix_sortie = bool(sec.charger_config()["entrees"].get("voix", True))
        self._avis_voix = False
        self.en_attente = False          # vrai quand KITT attend une réponse (oui/non ou suite)

    def log(self, msg):
        print(msg, flush=True)

    def parler(self, texte, memoriser=True):
        self.etat = "parle"
        self.log(f"KITT > {texte}")
        if memoriser:
            self.memoriser("assistant", texte)
        try:
            self._envoyer(texte)
        except Exception as e:
            self.log(f"[envoi Telegram échoué : {e}]")
        if self.voix_sortie:
            try:
                dire_voix(texte)
            except RuntimeError as e:
                if not self._avis_voix:
                    self._avis_voix = True
                    self.log(f"[voix indisponible : {e}]")
            except Exception as e:
                self.log(f"[synthèse vocale échouée : {e}]")
        self.etat = "veille"

    def regler_entree(self, nom, actif, persister=True):
        """« active la voix » : KITT répond aussi en message vocal. Les gestes ne sont pas disponibles ici."""
        if nom != "voix":
            return super().regler_entree(nom, actif, persister)
        if actif and not voix_disponible():
            return ("La voix demande espeak-ng et ffmpeg sur le serveur : "
                    "sudo apt install espeak-ng ffmpeg")
        self.voix_sortie = actif
        self._avis_voix = False
        if persister:
            cfg = sec.charger_config()
            cfg["entrees"]["voix"] = bool(actif)
            sec.sauver_config(cfg)
        return ("Voix activée. Je vous répondrai aussi en message vocal." if actif
                else "Voix désactivée. Je vous répondrai par écrit seulement.")

    def ecouter(self, timeout=3, actif=False):
        """La « saisie » est le prochain message Telegram, seulement pendant l'attente."""
        self.en_attente = True
        try:
            return self.texte_q.get(timeout=timeout), True
        except queue.Empty:
            return "", False
        finally:
            self.en_attente = False

    def confirmer(self, question):
        """Oui ou non. Le délai est long : on répond quand on veut, dans Telegram."""
        self.en_attente = True           # avant l'envoi : une réponse rapide ne doit pas être perdue
        rep = None
        try:
            self.parler(question + " " + kc.ton.phrase("confirme"))
            for _ in range(2):
                try:
                    texte = self.texte_q.get(timeout=900)
                except queue.Empty:
                    break
                rep = kc.reponse_oui_non(texte)
                if rep is not None:
                    break
                self.parler(kc.ton.phrase("pas_compris"))
        finally:
            self.en_attente = False
        rep = bool(rep)
        self.mem.exe("INSERT INTO journal VALUES (?,?,?)",
                     (kc.datetime.now().isoformat(timespec="seconds"), "confirmation",
                      f"{question[:120]} -> {'oui' if rep else 'non'}"))
        return rep


# ---------------------------------------------------------------- état partagé
BOT = None
BOUCLE = None
K = None
TACHES = queue.Queue()               # toutes les opérations sur la base passent ici, dans un seul thread
MESSAGES_LONGS = {}


def decouper(texte):
    texte = texte or "…"
    while len(texte) > LONGUEUR_MESSAGE:
        coupe = texte.rfind("\n", 0, LONGUEUR_MESSAGE)
        if coupe < 1:
            coupe = LONGUEUR_MESSAGE
        yield texte[:coupe]
        texte = texte[coupe:].lstrip("\n")
    yield texte


def envoyer(texte):
    """Appelé depuis le thread de KITT : envoie au propriétaire et attend la confirmation."""
    for morceau in decouper(texte):
        futur = asyncio.run_coroutine_threadsafe(
            BOT.send_message(chat_id=PROPRIETAIRE, text=morceau), BOUCLE)
        futur.result(timeout=60)


def travailleur():
    """Un seul thread exécute les commandes et les tâches de fond, dans l'ordre."""
    while True:
        tache = TACHES.get()
        try:
            tache()
        except Exception as e:
            print(f"[erreur de tâche : {e}]", flush=True)
        finally:
            TACHES.task_done()


def commande_utilisateur(texte):
    K.log(f"Vous > {texte}")
    K.memoriser("user", texte)
    K.traiter(texte)


def tache_de_fond():
    K.verifier_rappels()
    K.verifier_minuteurs()
    K.chats.maybe_save()
    kx.verifier_serveur(envoyer)


def surveillance():
    """Toutes les 30 secondes : rappels de rendez-vous et minuteurs."""
    while True:
        time.sleep(30)
        if TACHES.empty():
            TACHES.put(tache_de_fond)


def acheminer(texte):
    """Un message du propriétaire : réponse attendue, ou nouvelle commande."""
    if K.en_attente:
        K.texte_q.put(texte)          # réponse attendue (oui/non, suite d'une commande)
    else:
        TACHES.put(lambda: commande_utilisateur(texte))


def proprietaire(update):
    return update.effective_user is not None and update.effective_user.id == PROPRIETAIRE


async def repondre_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not proprietaire(update):
        return                        # inconnu : aucune réponse, aucune trace
    texte = (update.message.text or "").strip()
    if texte:
        acheminer(texte)


# ---------------------------------------------------------------- messages vocaux
MODELE_VOSK = None


def transcrire(ogg):
    """Message vocal Telegram (OGG) -> texte, avec Vosk et ffmpeg. Lève RuntimeError si indisponible."""
    global MODELE_VOSK
    if kc.KaldiRecognizer is None:
        raise RuntimeError("Vosk n'est pas installé (pip install vosk)")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg n'est pas installé (sudo apt install ffmpeg)")
    dossier = kc.trouver_modele()
    if dossier is None:
        raise RuntimeError("le modèle de reconnaissance vocale français est absent (voir README_SERVEUR.md)")
    if MODELE_VOSK is None:
        MODELE_VOSK = kc.Model(str(dossier))
    wav = ogg.with_suffix(".wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(ogg), "-ar", "16000", "-ac", "1", str(wav)],
                   check=True, timeout=120)
    rec = kc.KaldiRecognizer(MODELE_VOSK, 16000)
    with wave.open(str(wav), "rb") as w:
        while data := w.readframes(4000):
            rec.AcceptWaveform(data)
    return json.loads(rec.FinalResult()).get("text", "").strip()


async def repondre_vocal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not proprietaire(update):
        return
    dossier = Path(tempfile.mkdtemp(prefix="kitt-vocal-"))
    try:
        fichier = await context.bot.get_file(update.message.voice.file_id)
        ogg = dossier / "message.ogg"
        await fichier.download_to_drive(ogg)
        texte = await asyncio.to_thread(transcrire, ogg)
    except Exception as e:
        await update.message.reply_text(f"Je n'ai pas pu traiter le message vocal : {e}")
        return
    finally:
        shutil.rmtree(dossier, ignore_errors=True)
    if not texte:
        await update.message.reply_text("Je n'ai rien entendu.")
        return
    await update.message.reply_text(f"J'ai compris : « {texte} »")
    acheminer(texte)


# ---------------------------------------------------------------- sauvegarde envoyée sur Telegram
def creer_sauvegarde():
    """Copie cohérente de la base (sans arrêter KITT) et des conversations, dans une archive zip."""
    import zipfile
    from datetime import datetime
    dossier = Path(tempfile.mkdtemp(prefix="kitt-sauvegarde-"))
    horodatage = datetime.now().strftime("%Y%m%d-%H%M")
    copie = dossier / "kitt.db"
    destination = sqlite3.connect(copie)
    try:
        K.mem.c.backup(destination)
    finally:
        destination.close()
    archive = dossier / f"kitt-sauvegarde-{horodatage}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(copie, "kitt.db")
        if kc.CONVERSATIONS.exists():
            z.write(kc.CONVERSATIONS, "conversations.json")
    copie.unlink()
    return archive


def sauvegarde_telegram(k, t):
    archive = creer_sauvegarde()
    try:
        envoyer_document(archive, archive.name)
    finally:
        shutil.rmtree(archive.parent, ignore_errors=True)
    return "Sauvegarde envoyée. Gardez ce fichier en lieu sûr : il contient vos données."


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user is None or update.effective_user.id != PROPRIETAIRE:
        return
    await update.message.reply_text(f"Bonsoir {sec.charger_config()['prenom']}, KITT est en ligne. "
                                    "Écrivez-moi comme vous le feriez à l'oral. Tapez « qui es-tu ? » si vous voulez "
                                    "faire connaissance.")


async def au_demarrage(app: Application):
    global BOT, BOUCLE
    BOT = app.bot
    BOUCLE = asyncio.get_running_loop()
    threading.Thread(target=travailleur, daemon=True).start()
    threading.Thread(target=surveillance, daemon=True).start()
    TACHES.put(lambda: K.parler(kc.ton.accueil(kc.NOM)))


async def a_l_arret(app: Application):
    K.chats.flush()


DERNIERE_SIMULATION = {}


def labo_recherche(k, t):
    """« labo recherche effet Doppler » : réponse fondée sur Wikipédia, sources citées."""
    sujet = kr.extraire_sujet(t)
    if not sujet:
        return "Que dois-je chercher ? Exemple : labo recherche effet Doppler."
    try:
        sources = kr.rechercher(sujet)
    except kr.RechercheIndisponible as e:
        return str(e)
    if not sources:
        return f"Je ne trouve rien sur « {sujet} » dans Wikipédia. Essayez d'autres mots."
    try:
        return kr.repondre(sujet, sources, kc.generer)
    except kc.ErreurLLM as e:
        liens = "\n".join(f"- {s['titre']} : {s['url']}" for s in sources)
        return f"Le modèle local n'a pas pu résumer ({e}). Sources à lire :\n{liens}"


def labo3d_envoye(fonction):
    """Le labo 3D écrit un fichier HTML autonome : on l'envoie sur Telegram au lieu de l'ouvrir."""
    def lancer(k, t):
        DERNIERE_SIMULATION.clear()
        rep = fonction(k, t)
        if not DERNIERE_SIMULATION:
            return rep
        chemin = DERNIERE_SIMULATION["chemin"]
        envoyer_document(chemin, chemin.name)
        return (rep or "").replace("Simulation ouverte dans votre navigateur.",
                                   "Simulation jointe : ouvrez le fichier dans votre navigateur.")
    return lancer


def preparer():
    """Dossiers, modules d'extension, retrait des modules liés à la machine."""
    for d in kc.DOSSIERS_A_SAUVEGARDER + [kc.DOSSIER_FICHIERS]:
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    try:
        kitt_skills.enregistrer(kc.skill, kc.PASSE, kc.SKILLS)
        kitt_idees.configurer(kc.generer)
    except Exception as e:
        print(f"[modules d'extension indisponibles : {e}]", flush=True)
    kc.SKILLS[:] = [s for s in kc.SKILLS
                    if s[0] not in MODULES_RETIRES and not s[0].startswith("app_")]
    _generer_origine = kl3.generer

    def generer_sans_navigateur(scenario, parametres, ouvrir=True):
        chemin = _generer_origine(scenario, parametres, ouvrir=False)
        DERNIERE_SIMULATION["chemin"] = chemin
        return chemin
    kl3.generer = generer_sans_navigateur
    for i, (nom, decl, fn) in enumerate(kc.SKILLS):
        if nom == "labo3d":
            kc.SKILLS[i] = (nom, decl, labo3d_envoye(fn))
    kc.skill("labo_recherche", kr.DECLENCHEURS)(labo_recherche)
    kc.SKILLS.insert(0, kc.SKILLS.pop())      # avant le module « labo » qui intercepte le mot « labo »
    kc.skill("sauvegarde_telegram", ["envoie la sauvegarde", "sauvegarde moi", "exporte mes donnees",
                                     "exporte mes données"])(sauvegarde_telegram)


def main():
    global K
    if not TOKEN:
        sys.exit("TELEGRAM_TOKEN manquant : renseignez-le dans .env ou dans l'environnement.")
    if not PROPRIETAIRE:
        sys.exit("TELEGRAM_OWNER_ID manquant : indiquez votre identifiant Telegram numérique.")
    preparer()
    sec.charger_config()
    for avertissement in sec.avertissements():
        print(f"[config] {avertissement}", flush=True)
    K = KittServeur(envoyer)
    app = (Application.builder().token(TOKEN)
           .post_init(au_demarrage).post_shutdown(a_l_arret).build())
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, repondre_message))
    app.add_handler(MessageHandler(filters.VOICE, repondre_vocal))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
