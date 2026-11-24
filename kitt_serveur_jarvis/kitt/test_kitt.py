"""Tests de securite et de fonctionnement de KITT. Lancer : python -m unittest test_kitt -v"""
import json
import math
import os
import sys
import unicodedata
import zipfile
import sqlite3
import tempfile
import unittest
from pathlib import Path

# Dossier personnel isole : les tests n'ecrivent jamais dans le vrai ~/.kitt
_TMP = tempfile.mkdtemp()
os.environ["HOME"] = _TMP
os.environ["USERPROFILE"] = _TMP          # Path.home() lit USERPROFILE sous Windows

import kitt_securite as sec  # noqa: E402
import kitt_skills as ks     # noqa: E402
import kitt_ton as ton       # noqa: E402
import kitt_initiatives as ki  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402


class FakeMem:
    """Meme table « contacts » que la base de KITT (kitt.db), en memoire."""
    def __init__(self):
        self.c = sqlite3.connect(":memory:", check_same_thread=False)
        self.c.execute("CREATE TABLE contacts(nom TEXT PRIMARY KEY, email TEXT)")

    def exe(self, sql, args=()):
        cur = self.c.execute(sql, args)
        self.c.commit()
        return cur.fetchall()


class Stub:
    """Remplace l'objet Kitt : confirmation simulee, base de contacts en memoire."""
    def __init__(self, reponse=True):
        self.reponse = reponse
        self.questions = []
        self.mem = FakeMem()

    def confirmer(self, question):
        self.questions.append(question)
        return self.reponse


class Base(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        sec.DOSSIER = self.dossier
        sec.CONFIG = self.dossier / "config.json"
        sec.DOSSIER_SKILLS = self.dossier / "skills"


class TestValidation(Base):
    def test_noms_de_skills(self):
        self.assertTrue(sec.nom_valide("meteo"))
        self.assertFalse(sec.nom_valide("../etc"))
        self.assertFalse(sec.nom_valide("a"))
        self.assertFalse(sec.nom_valide("Meteo"))
        self.assertFalse(sec.nom_valide("x" * 40))

    def test_chemin_hors_dossier_refuse(self):
        with self.assertRaises(ValueError):
            sec.chemin_dans(self.dossier, "../passwd")

    def test_numeros(self):
        self.assertEqual(sec.normaliser_numero("06 77 12 34 56"), "+237677123456")
        self.assertEqual(sec.normaliser_numero("+33 6 12 34 56 78"), "+33612345678")
        self.assertEqual(sec.normaliser_numero("0012345"), None)
        self.assertIsNone(sec.normaliser_numero("; rm -rf /"))

    def test_texte_nettoye_et_limite(self):
        self.assertNotIn("\x00", sec.nettoyer_texte("bon\x00jour"))
        self.assertEqual(len(sec.nettoyer_texte("a" * 900, 500)), 500)

    def test_limiteur(self):
        l = sec.Limiteur(2)
        self.assertTrue(l.autorise())
        self.assertTrue(l.autorise())
        self.assertFalse(l.autorise())


class TestReseau(Base):
    def test_coupe_par_defaut(self):
        self.assertFalse(sec.reseau_active("meteo"))
        self.assertFalse(sec.url_autorisee("meteo", "https://api.open-meteo.com/v1/x"))

    def test_active_puis_seuls_domaines_autorises(self):
        ks.activer_reseau("meteo", True)
        self.assertTrue(sec.url_autorisee("meteo", "https://api.open-meteo.com/v1/forecast"))
        self.assertFalse(sec.url_autorisee("meteo", "http://api.open-meteo.com/v1/forecast"))
        self.assertFalse(sec.url_autorisee("meteo", "https://evil.example.com/"))
        self.assertFalse(sec.url_autorisee("meteo", "https://user@api.open-meteo.com/"))
        self.assertFalse(sec.url_autorisee("youtube", "https://www.youtube.com/"))

    def test_service_inconnu_refuse(self):
        self.assertIn("Service inconnu", ks.activer_reseau("ftp", True))

    def test_meteo_sans_reseau(self):
        self.assertIn("active internet", ks.cmd_meteo(Stub(), "météo"))

    def test_whatsapp_sans_reseau(self):
        self.assertIn("active internet", ks.cmd_whatsapp(Stub(), "whatsapp à marc dis lui salut"))

    def test_whatsapp_annule_si_non_confirme(self):
        ks.activer_reseau("whatsapp", True)
        k = Stub(reponse=False)
        ks.cmd_numero(k, "ajoute le numéro de Marc 06 77 12 34 56")
        rep = ks.cmd_whatsapp(k, "whatsapp à marc dis lui bonjour")
        self.assertIn(rep, ton.PHRASES["annule"])
        self.assertIn("marc", k.questions[0].lower())

    def test_whatsapp_sans_numero_donne_la_marche_a_suivre(self):
        ks.activer_reseau("whatsapp", True)
        k = Stub()
        k.mem.exe("INSERT INTO contacts VALUES ('Paul', 'paul@exemple.com')")
        self.assertIn("ajoute le numéro", ks.cmd_whatsapp(k, "whatsapp à paul dis lui salut"))


class TestInstallateur(Base):
    def test_installer_et_desinstaller(self):
        self.assertIn("installé", ks.installer("blague"))
        self.assertIn("blague", ks.installes())
        self.assertIn("désinstallé", ks.desinstaller("blague"))
        self.assertNotIn("blague", ks.installes())

    def test_skill_inconnu_refuse(self):
        self.assertIn("inconnu", ks.installer("../../evil"))
        self.assertFalse((self.dossier / "evil.json").exists())

    def test_desinstaller_chemin_malveillant(self):
        self.assertIn("invalide", ks.desinstaller("../config"))

    def test_manifeste_prive(self):
        ks.installer("blague")
        mode = os.stat(sec.chemin_dans(sec.DOSSIER_SKILLS, "blague")).st_mode & 0o777
        if os.name == "posix":
            self.assertEqual(mode, 0o600)

    def test_manifeste_altere_ignore(self):
        sec.DOSSIER_SKILLS.mkdir(parents=True, exist_ok=True)
        (sec.DOSSIER_SKILLS / "bizarre.json").write_text('{"type":"python","code":"import os"}')
        self.assertNotIn("bizarre", ks.installes())


class TestRecettes(Base):
    def test_creation_valide(self):
        rep = ks.creer_recette("salut_matin", ["bonjour", "salut matin"], "Bonjour Michael !")
        self.assertIn("créé", rep)
        d = json.loads(sec.chemin_dans(sec.DOSSIER_SKILLS, "salut_matin").read_text(encoding="utf-8"))
        self.assertEqual(d["type"], "recette")
        self.assertEqual(d["reponse"], "Bonjour Michael !")

    def test_refus_nom_reserve_et_declencheurs_dangereux(self):
        self.assertIn("réservé", ks.creer_recette("meteo", ["x y"], "rep"))
        self.assertIn("invalide", ks.creer_recette("bon", ["re:.*"], "rep"))
        self.assertIn("invalide", ks.creer_recette("bon", ["(a+)+$ bad"], "rep"))
        self.assertIn("vide", ks.creer_recette("bon", ["bonjour"], "   "))

    def test_recette_ne_contient_aucun_code(self):
        ks.creer_recette("cmd", ["ouvre cmd"], "import os; os.system('x')")
        d = json.loads(sec.chemin_dans(sec.DOSSIER_SKILLS, "cmd").read_text(encoding="utf-8"))
        self.assertEqual(d["type"], "recette")
        self.assertIn("import os", d["reponse"])  # c'est du texte, jamais exécuté

    def test_suppression_coupe_la_recette(self):
        ks.creer_recette("salut_matin", ["bonjour"], "Salut")
        ks.desinstaller("salut_matin")
        self.assertIsNone(ks.lire_manifeste("salut_matin"))


class TestCommandes(Base):
    def test_numero_enregistre_dans_la_base_puis_appel(self):
        k = Stub()
        self.assertIn("enregistré", ks.cmd_numero(k, "ajoute le numéro de Marc 06 77 12 34 56"))
        self.assertEqual(ks.trouver_contact(k, "appelle marc"), ("Marc", "+237677123456"))
        # le contact est bien dans la table existante, avec sa colonne telephone
        self.assertEqual(k.mem.exe("SELECT telephone FROM contacts WHERE nom='Marc'"),
                         [("+237677123456",)])

    def test_numero_nouveau_contact_nom_compose(self):
        k = Stub()
        ks.cmd_numero(k, "ajoute le numéro de Marc Dupont 0677123456")
        self.assertEqual(ks.trouver_contact(k, "appelle marc dupont")[0], "Marc Dupont")

    def test_numero_mis_a_jour_pour_contact_existant(self):
        k = Stub()
        k.mem.exe("INSERT INTO contacts VALUES ('Marc', 'marc@exemple.com')")
        ks.cmd_numero(k, "ajoute le numéro de marc 0611223344")
        self.assertEqual(k.mem.exe("SELECT email, telephone FROM contacts WHERE nom='Marc'"),
                         [("marc@exemple.com", "+237611223344")])

    def test_appel_numero_injecte_refuse(self):
        k = Stub()
        self.assertEqual(ks.trouver_contact(k, "appelle 0677123456"), ("+237677123456", "+237677123456"))
        self.assertEqual(ks.trouver_contact(k, "appelle ; rm -rf /"), (None, None))

    def test_migration_colonne_telephone(self):
        k = Stub()
        ks.assurer_colonne_telephone(k)
        colonnes = [r[1] for r in k.mem.exe("PRAGMA table_info(contacts)")]
        self.assertIn("telephone", colonnes)
        ks.assurer_colonne_telephone(k)   # deuxieme appel : pas d'erreur

    def test_numero_invalide_refuse(self):
        self.assertIn("ajoute le numéro", ks.cmd_numero(Stub(), "ajoute le numéro de Marc 12"))

    def test_blague_et_echecs(self):
        reponse = ks.cmd_blague(Stub(), "")
        self.assertTrue(any(reponse.endswith(b) for b in ks.BLAGUES))
        self.assertIn(ks.cmd_echecs(Stub(), ""), [p.format(prenom="Michael") for p in ton.PHRASES["echecs"]])

    def test_jeu_inconnu_ne_lance_rien(self):
        sec.CONFIG.write_text(json.dumps({"jeux": {"minecraft": "/bin/true"}}), encoding="utf-8")
        self.assertIn("Jeux disponibles", ks.cmd_jeux(Stub(), "joue a gta"))

    def test_jeu_configure_sans_shell(self):
        sec.CONFIG.write_text(json.dumps({"jeux": {"demo": "/nope/absent.exe"}}), encoding="utf-8")
        self.assertIn("Je ne trouve pas", ks.cmd_jeux(Stub(), "joue a demo"))

    def test_youtube_sans_reseau(self):
        self.assertIn("active internet", ks.cmd_youtube(Stub(), "youtube k2000"))


class TestTon(unittest.TestCase):
    def test_pas_de_repetition_immediate(self):
        ton._derniers.clear()
        prec = None
        for _ in range(200):
            t = ton.phrase("inconnu", prenom="Michael")
            self.assertNotEqual(t, prec)
            prec = t

    def test_toutes_les_formulations_sont_utilisees(self):
        ton._derniers.clear()
        vus = {ton.phrase("echecs", prenom="M") for _ in range(300)}
        self.assertEqual(vus, {p.format(prenom="M") for p in ton.PHRASES["echecs"]})

    def test_champs_absents_ne_plantent_pas(self):
        self.assertNotIn("{", ton.phrase("accueil_soir"))     # pas de prenom fourni
        self.assertNotIn("{", ton.phrase("meteo_ville", ville="Batouri", temp="28"))

    def test_moments_de_la_journee(self):
        self.assertEqual(ton.moment(7), "matin")
        self.assertEqual(ton.moment(14), "apresmidi")
        self.assertEqual(ton.moment(20), "soir")
        self.assertEqual(ton.moment(2), "nuit")

    def test_accueil_selon_l_heure(self):
        self.assertIn(ton.accueil("Michael", 8),
                      [p.format(prenom="Michael") for p in ton.PHRASES["accueil_matin"]])
        self.assertIn(ton.accueil("Michael", 23),
                      [p.format(prenom="Michael") for p in ton.PHRASES["accueil_nuit"]])

    def test_conseil_meteo(self):
        self.assertIn(ton.conseil_meteo(15), ton.PHRASES["meteo_frais"])
        self.assertIn(ton.conseil_meteo(35), ton.PHRASES["meteo_chaud"])
        self.assertIn(ton.conseil_meteo(27), ton.PHRASES["meteo_doux"])


class TestInitiatives(Base):
    def setUp(self):
        super().setUp()
        self.ini = ki.Initiatives()
        self.t0 = datetime(2026, 10, 9, 14, 0)

    def test_pause_apres_90_minutes_seulement(self):
        self.ini.activite(self.t0)
        self.assertEqual(self.ini.decider(self.t0 + timedelta(minutes=89), {}, "Michael"), [])
        out = self.ini.decider(self.t0 + timedelta(minutes=91), {}, "Michael")
        self.assertEqual([c for c, _ in out], ["pause"])

    def test_pause_non_repetee_avant_le_delai(self):
        self.ini.activite(self.t0)
        t = self.t0 + timedelta(minutes=95)
        self.ini.annoncer("pause", t)
        self.assertEqual(self.ini.decider(t + timedelta(minutes=10), {}, "M"), [])

    def test_nouvelle_session_apres_30_min_inactivite(self):
        self.ini.activite(self.t0)
        self.ini.activite(self.t0 + timedelta(minutes=120))  # 2 h sans commande : nouvelle session
        self.assertEqual(self.ini.debut_session, self.t0 + timedelta(minutes=120))

    def test_batterie_faible_debranchee(self):
        out = self.ini.decider(self.t0, {"batterie": (12, False)}, "M")
        self.assertEqual([c for c, _ in out], ["batterie"])
        self.assertEqual(self.ini.decider(self.t0, {"batterie": (12, True)}, "M"), [])
        self.assertEqual(self.ini.decider(self.t0, {"batterie": (60, False)}, "M"), [])

    def test_heure_tardive_seulement_si_active(self):
        nuit = datetime(2026, 10, 9, 23, 30)
        self.assertEqual(self.ini.decider(nuit, {}, "M"), [])          # personne n'est la
        self.ini.activite(nuit)
        self.assertEqual([c for c, _ in self.ini.decider(nuit, {}, "M")], ["tard"])

    def test_disque_et_taches(self):
        out = self.ini.decider(self.t0, {"disque_libre_pct": 3, "taches": 7}, "M")
        self.assertEqual({c for c, _ in out}, {"disque", "taches"})

    def test_taches_pas_la_nuit(self):
        nuit = datetime(2026, 10, 9, 2, 0)
        self.assertEqual(self.ini.decider(nuit, {"taches": 9}, "M"), [])

    def test_messages_sans_champ_manquant(self):
        for cle, msg in self.ini.decider(self.t0, {"batterie": (10, False), "taches": 6,
                                                   "disque_libre_pct": 2}, "Michael"):
            self.assertNotIn("{", msg)

    def test_interrupteur_vocal(self):
        ks.cmd_initiatives(Stub(), "desactive les initiatives")
        self.assertFalse(sec.charger_config()["initiatives"]["activees"])
        ks.cmd_initiatives(Stub(), "active les initiatives")
        self.assertTrue(sec.charger_config()["initiatives"]["activees"])

    def test_pause_bornee_par_la_config(self):
        cfg = sec.charger_config()
        self.assertGreaterEqual(cfg["initiatives"]["pause_minutes"], 30)


class TestHabitudes(Base):
    def setUp(self):
        super().setUp()
        self.k = Stub()

    def _sessions(self, n, debut_h, duree_min):
        """n sessions passees de duree donnee, commencant a debut_h."""
        ki._assurer_table(self.k.mem)
        for i in range(n):
            d = datetime(2026, 10, 1 + i, debut_h, 0)
            f = d + timedelta(minutes=duree_min)
            self.k.mem.exe("INSERT INTO sessions VALUES (?,?)",
                           (d.isoformat(timespec="seconds"), f.isoformat(timespec="seconds")))

    def test_rien_appris_avant_cinq_sessions(self):
        self._sessions(3, 9, 60)
        profil = ki.apprendre(self.k.mem)
        self.assertIsNone(profil["pause_min"])
        self.assertIn("encore observer", ki.resume(profil))

    def test_pause_apprise_depuis_les_sessions(self):
        self._sessions(6, 9, 60)
        self.assertEqual(ki.apprendre(self.k.mem)["pause_min"], 60)

    def test_coucher_appris_depuis_la_fin_des_sessions(self):
        self._sessions(6, 22, 60)            # chaque session finit a 23 h
        self.assertAlmostEqual(ki.apprendre(self.k.mem)["coucher"], 23.5)

    def test_activite_enregistre_et_prolonge_la_session(self):
        ini = ki.Initiatives()
        t0 = datetime(2026, 10, 9, 15, 0)
        ini.activite(t0, self.k.mem)
        ini.activite(t0 + timedelta(minutes=20), self.k.mem)
        self.assertEqual(self.k.mem.exe("SELECT fin FROM sessions"),
                         [((t0 + timedelta(minutes=20)).isoformat(timespec="seconds"),)])

    def test_pause_apprise_remplace_la_valeur_fixe(self):
        ini = ki.Initiatives()
        ini.profil = {"pause_min": 60, "coucher": None, "sessions": 9}
        self.assertEqual(ini.pause_effective(90, auto=True), 60)
        self.assertEqual(ini.pause_effective(90, auto=False), 90)

    def test_coucher_appris_declenche_le_rappel_plus_tot(self):
        ini = ki.Initiatives()
        soir = datetime(2026, 10, 9, 22, 30)
        ini.activite(soir)
        self.assertEqual(ini.decider(soir, {}, "M", coucher=22.0)[0][0], "tard")
        self.assertEqual(ini.decider(soir, {}, "M", coucher=None), [])

    def test_commande_mes_habitudes(self):
        self._sessions(6, 9, 60)
        rep = ks.cmd_habitudes(self.k, "mes habitudes")
        self.assertIn("60 minutes", rep)


class TestRelectureKitt(unittest.TestCase):
    """Points trouves lors de la relecture de kitt_complet.py."""

    @classmethod
    def setUpClass(cls):
        import kitt_complet
        cls.K = kitt_complet

    def test_confirmation_negation_prioritaire(self):
        K = self.K
        cas = {"oui": True, "d'accord": True, "d accord": True, "ok vas y": True, "bien sûr": True,
               "pas d'accord": False, "non": False, "annule": False, "refuse": False,
               "surtout pas": False, "non pas maintenant": False, "je ne sais pas": False,
               "peut-être": None, "": None}
        for texte, attendu in cas.items():
            self.assertEqual(K.reponse_oui_non(texte), attendu, texte)

    def test_nettoyage_limite_au_dossier_kitt(self):
        K = self.K
        import time
        ancien = time.time() - 30 * 86400
        with tempfile.TemporaryDirectory() as racine:
            K.DOSSIER_TEMP = Path(racine) / "kitt_tmp"
            K.DOSSIER_TEMP.mkdir()
            mien = K.DOSSIER_TEMP / "vieux.tmp"
            mien.write_text("x" * 1000)
            os.utime(mien, (ancien, ancien))
            autre = Path(racine) / "autre_appli.tmp"      # hors du dossier de KITT : doit rester
            autre.write_text("y" * 1000)
            os.utime(autre, (ancien, ancien))
            K.nettoyer_temp(jours=7)
            self.assertFalse(mien.exists())
            self.assertTrue(autre.exists())

    def test_dire_duree_sans_masquer_le_module(self):
        self.assertEqual(self.K.dire_duree(3725), "1 heure 2 minutes 5 secondes")


class TestModeleLLM(Base):
    def test_defaut_mistral(self):
        self.assertEqual(sec.charger_config()["modele_llm"], "qwen2.5-kitt")

    def test_modele_configurable(self):
        sec.CONFIG.write_text(json.dumps({"modele_llm": "qwen2.5-kitt"}), encoding="utf-8")
        self.assertEqual(sec.charger_config()["modele_llm"], "qwen2.5-kitt")

    def test_modele_invalide_ignore(self):
        for mauvais in ["../../x", "a b", "x" * 80, ["liste"], ""]:
            sec.CONFIG.write_text(json.dumps({"modele_llm": mauvais}), encoding="utf-8")
            self.assertEqual(sec.charger_config()["modele_llm"], "qwen2.5-kitt", mauvais)


import kitt_fiabilite as fi  # noqa: E402
import kitt_applications as ka  # noqa: E402
import kitt_calcul as kc  # noqa: E402
import kitt_aide as kai  # noqa: E402
import kitt_idees as kid  # noqa: E402
import kitt_web as kw  # noqa: E402
import kitt_gestes as kg  # noqa: E402
import kitt_labo3d as kl3b  # noqa: E402
import threading  # noqa: E402
import urllib.request  # noqa: E402
import urllib.error  # noqa: E402
import kitt_labo as kl  # noqa: E402
import kitt_labo3d as kl3  # noqa: E402
from unittest import mock  # noqa: E402
import tempfile  # noqa: E402


class TestFiabilite(unittest.TestCase):
    def test_nettoyage_des_marqueurs(self):
        self.assertEqual(fi.nettoyer("<|assistant|>KITT : Bonjour Michael.</s>"), "Bonjour Michael.")
        self.assertEqual(fi.nettoyer("Réponse : oui"), "oui")

    def test_detection_langue(self):
        self.assertTrue(fi.est_francais("Le ciel est bleu par temps clair, et il fait beau."))
        self.assertFalse(fi.est_francais("The sky is blue on a clear day and it is very nice."))
        self.assertTrue(fi.est_francais("Oui."))   # trop court pour trancher

    def test_nouvelle_tentative_en_francais(self):
        appels = []

        def produire(systeme, consigne):
            appels.append(systeme)
            if "uniquement en français" in systeme:
                return "Le ciel est bleu par temps clair."
            return "The sky is blue on a clear day and it is very nice."
        self.assertEqual(fi.generer_verifie(produire, "Sys", "Q"), "Le ciel est bleu par temps clair.")
        self.assertEqual(len(appels), 2)

    def test_pas_de_nouvelle_tentative_si_francais(self):
        appels = []

        def produire(systeme, consigne):
            appels.append(1)
            return "Le ciel est bleu par temps clair."
        fi.generer_verifie(produire, "Sys", "Q")
        self.assertEqual(len(appels), 1)

    def test_passages_pertinents(self):
        doc = ("Les tarifs de la cantine sont fixés chaque année. " * 20 +
               "Le rendez-vous avec le directeur est fixé au mardi 12 novembre à dix heures. " +
               "Le parking est ouvert le matin. " * 20)
        extraits = fi.passages(doc, "Quand est le rendez-vous avec le directeur ?")
        self.assertTrue(extraits)
        self.assertIn("mardi 12 novembre", " ".join(extraits))

    def test_aucun_passage_si_question_hors_document(self):
        doc = "Le parking est ouvert le matin. " * 40
        self.assertEqual(fi.passages(doc, "Quel est le prix du billet de train ?"), [])

    def test_mots_vides_ignores(self):
        self.assertEqual(fi.mots_cles("Quel est le prix ?"), {"prix"})

    def test_evaluation(self):
        cas = [{"question": "Capitale ?", "doit": ["yaounde"]},
               {"question": "7 x 8 ?", "doit": ["56"], "interdit": ["54"]}]
        reponses = {"Capitale ?": "La capitale est Yaoundé.", "7 x 8 ?": "Cela fait 56."}
        reussis, total, echecs = fi.evaluer(lambda s, c: reponses[c], cas)
        self.assertEqual((reussis, total, echecs), (2, 2, []))
        reponses["7 x 8 ?"] = "54"
        reussis, total, echecs = fi.evaluer(lambda s, c: reponses[c], cas)
        self.assertEqual(reussis, 1)
        self.assertEqual(echecs[0][0], "7 x 8 ?")


class TestApplications(Base):
    def setUp(self):
        super().setUp()
        self.menu = self.dossier / "menu"
        self.menu.mkdir()
        for nom in ["Mozilla Firefox.lnk", "Mozilla Thunderbird.lnk", "Calculatrice.lnk",
                    "Windows PowerShell.lnk", "Invite de commandes.lnk"]:
            (self.menu / nom).write_text("x")
        (self.menu / "Gimp.desktop").write_text("[Desktop Entry]\nName=Gimp\nNoDisplay=true\n")
        (self.menu / "Inkscape.desktop").write_text("[Desktop Entry]\nName=Inkscape\n")
        self.p = mock.patch.object(ka, "dossiers_recherche", return_value=[self.menu])
        self.p.start()

    def tearDown(self):
        self.p.stop()
        super().tearDown()

    def test_decouverte_exclut_outils_systeme_et_caches(self):
        cles = set(ka.decouvrir([self.menu]))
        self.assertIn("calculatrice", cles)
        self.assertIn("inkscape", cles)
        self.assertNotIn("windows powershell", cles)
        self.assertNotIn("invite de commandes", cles)
        self.assertNotIn("gimp", cles)            # NoDisplay=true : cachee

    def test_outils_interdits(self):
        self.assertTrue(ka.est_interdit("Windows PowerShell"))
        self.assertTrue(ka.est_interdit("regedit"))
        self.assertTrue(ka.est_interdit("Installer Chrome"))
        self.assertTrue(ka.est_interdit("Invite de commandes"))
        self.assertTrue(ka.est_interdit("Éditeur du registre"))
        self.assertTrue(ka.est_interdit("Planificateur de tâches"))
        self.assertFalse(ka.est_interdit("Calculatrice"))

    def test_recherche_exacte_partielle_ambigue_absente(self):
        self.assertEqual(ka.trouver("calculatrice")[0], "ok")
        self.assertEqual(ka.trouver("calcul")[0], "ok")
        self.assertEqual(ka.trouver("mozilla")[0], "ambigu")
        self.assertEqual(ka.trouver("photoshop")[0], "rien")
        self.assertEqual(ka.trouver("powershell")[0], "rien")

    def test_lancement_sans_shell(self):
        with mock.patch.object(ka.subprocess, "Popen") as popen, \
                mock.patch.object(ka.sys, "platform", "linux"), \
                mock.patch.object(ka.shutil, "which", return_value="/usr/bin/gtk-launch"):
            ka.lancer(str(self.menu / "Inkscape.desktop"))
        args, kwargs = popen.call_args
        self.assertNotIn("shell", kwargs)
        self.assertEqual(args[0], ["/usr/bin/gtk-launch", "Inkscape"])

    def test_ajout_chemin_relatif_ou_inexistant_refuse(self):
        self.assertIn("chemin complet", ka.ajouter_perso("Test", "app.exe"))
        self.assertIn("aucun fichier", ka.ajouter_perso("Test", str(self.dossier / "absent.exe")))

    def test_ajout_outil_admin_refuse(self):
        fichier = self.dossier / "ps.exe"
        fichier.write_text("x")
        self.assertIn("administration", ka.ajouter_perso("PowerShell", str(fichier)))

    def test_ajout_valide_puis_trouve(self):
        fichier = self.dossier / "monlogiciel"
        fichier.write_text("x")
        fichier.chmod(0o755)
        self.assertIn("ajoutée", ka.ajouter_perso("MonLogiciel", str(fichier)))
        self.assertEqual(ka.trouver("monlogiciel")[0], "ok")

    def test_phrase_qui_ne_commence_pas_par_le_verbe_ignoree(self):
        ks._H["passe"] = "PASSE"
        self.assertEqual(ks.cmd_ouvrir_app(Stub(), "je lance une réunion demain"), "PASSE")

    def test_ouverture_refusee_si_non_confirmee(self):
        ks._H["passe"] = "PASSE"
        k = Stub(reponse=False)
        with mock.patch.object(ka, "lancer") as lance:
            rep = ks.cmd_ouvrir_app(k, "ouvre calculatrice")
        self.assertIn(rep, ton.PHRASES["annule"])
        lance.assert_not_called()

    def test_ouverture_confirmee(self):
        ks._H["passe"] = "PASSE"
        with mock.patch.object(ka, "lancer", return_value=True) as lance:
            rep = ks.cmd_ouvrir_app(Stub(reponse=True), "ouvre la calculatrice")
        self.assertEqual(rep, "Calculatrice est lancé.")
        lance.assert_called_once()

    def test_ouverture_outil_interdit(self):
        ks._H["passe"] = "PASSE"
        self.assertIn("administration", ks.cmd_ouvrir_app(Stub(), "ouvre powershell"))

    def test_commande_ajout_parse_le_chemin(self):
        fichier = self.dossier / "app.exe"
        fichier.write_text("x")
        fichier.chmod(0o755)
        k = Stub(reponse=True)
        rep = ks.cmd_ajouter_app(k, f"ajoute l'application Mon Outil {fichier}")
        self.assertIn("ajoutée", rep)
        self.assertEqual(ka.trouver("mon outil")[0], "ok")


class TestCalculatrice(unittest.TestCase):
    def test_calculs_courants(self):
        cas = {"combien font 7 fois 8": "Le résultat est 56.",
               "calcule 17 pour cent de 2350": "Le résultat est 399,5.",
               "combien font 10 divisé par 4": "Le résultat est 2,5.",
               "combien font 2 puissance 10": "Le résultat est 1024.",
               "combien font -3 plus 5": "Le résultat est 2.",
               "calcule (2+3)*4": "Le résultat est 20.",
               "combien font 3 virgule 5 plus 1": "Le résultat est 4,5.",
               "combien font 5 au carré": "Le résultat est 25.",
               "combien font racine de 16": "Le résultat est 4.",
               "calcule sqrt(16)": "Le résultat est 4.",
               "combien font 7 % 3": "Le résultat est 1.",
               "combien font 17 pour 100 de 2350": "Le résultat est 399,5."}
        for texte, attendu in cas.items():
            self.assertEqual(kc.calculer(texte), attendu, texte)

    def test_refus_securite(self):
        for texte in ['calcule __import__("os")', "calcule open('x')", "calcule 1; import os",
                      "calcule 'abc'.upper()", "combien font 2 puissance 100000"]:
            rep = kc.calculer(texte)
            self.assertTrue(rep.startswith("Je ne peux pas"), texte + " -> " + rep)

    def test_erreurs_claires(self):
        self.assertIn("division par zéro", kc.calculer("combien font 1 divisé par 0"))
        self.assertIn("trop longue", kc.calculer("calcule " + "1+" * 150 + "1"))

    def test_pas_de_calcul(self):
        self.assertIn("Quel calcul", kc.calculer("combien font"))

    def test_moins_negatif_preserve(self):
        self.assertEqual(kc.expression_depuis_texte("calcule -3 fois 2"), "-3 * 2")

    def test_evaluer_sans_eval(self):
        with self.assertRaises(ValueError):
            kc.evaluer("__import__('os').system('x')")

    def test_calcul_installable_comme_les_autres(self):
        self.assertIn("calcul", ks.CATALOGUE)
        self.assertIn("calcul", ks._FONCTIONS)


class TestLaboPhysique(unittest.TestCase):
    def test_chute_sans_frottement_formule_exacte(self):
        r = kl.chute(10, objet={"masse": 1e9, "cx": 1, "surface": 1})
        self.assertAlmostEqual(r["t_frottement"], math.sqrt(2 * 10 / 9.81), delta=0.01)

    def test_chute_avec_frottement_plus_lente(self):
        r = kl.chute(100)
        self.assertGreater(r["t_frottement"], r["t_vide"])
        self.assertLess(r["vitesse_impact"], r["vitesse_vide"])
        self.assertLess(r["vitesse_impact"], r["vitesse_limite"] + 0.5)

    def test_pendule_grand_angle_exact(self):
        exacte, simple = kl.periode_pendule(1.0, 60)
        self.assertAlmostEqual(exacte / simple, 1.0732, delta=0.0005)
        exacte0, simple0 = kl.periode_pendule(1.0, 0.001)
        self.assertAlmostEqual(exacte0 / simple0, 1.0, delta=1e-6)

    def test_tir_sans_frottement_portee_theorique(self):
        r = kl.tir(20, 45, objet={"masse": 1e9, "cx": 1, "surface": 1})
        self.assertAlmostEqual(r["portee"], r["portee_vide"], delta=0.05)

    def test_tir_avec_frottement_porte_moins_loin(self):
        r = kl.tir(40, 45)
        self.assertLess(r["portee"], r["portee_vide"])
        self.assertGreater(r["portee"], 0)


class TestLabo3D(unittest.TestCase):
    def test_bornes_appliquees(self):
        self.assertEqual(kl3._bornee(10000, "chute"), 500.0)
        self.assertEqual(kl3._bornee(-5, "tir_vitesse"), 1.0)

    def test_extraction_des_nombres(self):
        self.assertEqual(kl3.parametres_depuis_texte("pendule", "labo 3d pendule 1,5 mètres 60 degrés"),
                         {"longueur": 1.5, "angle": 60.0})
        self.assertEqual(kl3.parametres_depuis_texte("chute", "labo 3d chute de 20 mètres"), {"hauteur": 20.0})

    def test_json_sur_pour_script(self):
        self.assertNotIn("</", kl3._json_sur({"t": "</script><b>"}))

    def test_page_autonome_sans_reseau(self):
        H = tempfile.mkdtemp()
        sec_home = sec.DOSSIER
        kl3.DOSSIER_SIMULATIONS = Path(H) / "simulations"
        with mock.patch.object(kl3.webbrowser, "open") as ouvre:
            chemin = kl3.generer("tir", {"vitesse": 30, "angle": 40}, ouvrir=True)
        page = chemin.read_text(encoding="utf-8")
        self.assertIn("const D =", page)
        self.assertEqual(page.count("</script>"), 1)
        self.assertNotIn("http://", page.replace("<!doctype", ""))  # aucune ressource distante
        self.assertNotIn("https://", page)
        ouvre.assert_called_once()
        self.assertEqual(chemin.stat().st_mode & 0o777, 0o600) if os.name == "posix" else None


class TestSkillLabo3D(Base):
    def test_labo_ancien_laisse_passer_la_3d(self):
        import kitt_complet as K
        self.assertEqual(K.labo(Stub(), "labo 3d chute de 10 mètres"), K.PASSE)

    def test_commande_sans_scenario(self):
        rep = ks.cmd_labo3d(Stub(), "labo 3d")
        self.assertIn(rep, ton.PHRASES["labo3d_aucun"] + ton.PHRASES.get("labo3d_aucun_chaleureux", []))

    def test_commande_chute(self):
        ks.kl3.DOSSIER_SIMULATIONS = Path(tempfile.mkdtemp())
        with mock.patch.object(ks.kl3.webbrowser, "open"):
            rep = ks.cmd_labo3d(Stub(), "labo 3d chute de 20 mètres")
        self.assertIn("Simulation ouverte", rep)
        self.assertTrue(any(ks.kl3.DOSSIER_SIMULATIONS.glob("chute_*.html")))


def _moteur_pret():
    """Enregistre une seule fois les skills (builtins et installables) dans le moteur de kitt_complet."""
    import kitt_complet as K
    if not getattr(_moteur_pret, "fait", False):
        ks.enregistrer(K.skill, K.PASSE, K.SKILLS)
        _moteur_pret.fait = True
    return K


class TestAide(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.K = _moteur_pret()

    def test_sommaire_couvre_tous_les_themes(self):
        sommaire = kai.sommaire()
        for cle, (titre, _r, _c) in kai.THEMES.items():
            self.assertIn(titre, sommaire, cle)

    def test_detail_par_theme(self):
        self.assertIn("rendez-vous", kai.reponse("aide agenda"))
        self.assertIn("labo 3d chute", kai.reponse("aide labo 3d"))
        self.assertIn("calcul", kai.reponse("aide calculatrice").lower())
        self.assertIn("Skills", kai.reponse("aide skills"))

    def test_sans_theme_sommaire(self):
        self.assertEqual(kai.reponse("que sais-tu"), kai.sommaire())

    def test_chaque_exemple_declenche_une_fonction(self):
        K = self.K
        declencheurs = [d for _nom, decl, _fn in K.SKILLS for d in decl]
        rates = []
        for cle, (_titre, _r, commandes) in kai.THEMES.items():
            for exemple, _effet in commandes:
                norm = K.sans_accents(exemple)
                if not any(K.correspond(d, norm) for d in declencheurs):
                    rates.append((cle, exemple))
        self.assertEqual(rates, [], "exemples qui ne declenchent rien")

    def test_aide_dans_le_moteur(self):
        K = self.K
        k = K.Kitt(None)
        self.assertIn("Agenda", K.aide(k, "que sais-tu"))


class TestRevueAnomalies(unittest.TestCase):
    """Regressions des anomalies trouvees lors de la revue du code."""

    def test_virgule_decimale(self):
        self.assertEqual(kc.calculer("calcule 3,5 fois 2"), "Le résultat est 7.")
        self.assertEqual(kc.calculer("combien font 17,5 pour cent de 200"), "Le résultat est 35.")
        self.assertEqual(kc.calculer("combien font 2 fois 0,5"), "Le résultat est 1.")

    def test_exposant_reel(self):
        self.assertEqual(kc.calculer("combien font 4 puissance 0,5"), "Le résultat est 2.")

    def test_racine_negative_sans_anglais(self):
        rep = kc.calculer("calcule sqrt(-4)")
        self.assertIn("négatif", rep)
        self.assertNotIn("domain", rep)

    def test_resultat_complexe_refuse(self):
        self.assertIn("résultat réel", kc.calculer("combien font (-8) puissance (1/3)"))

    def test_fonction_sans_argument(self):
        rep = kc.calculer("calcule min()")
        self.assertIn("au moins un nombre", rep)

    def test_simulations_jamais_ecrasees(self):
        H = Path(tempfile.mkdtemp())
        kl3.DOSSIER_SIMULATIONS = H
        with mock.patch.object(kl3.webbrowser, "open"):
            a = kl3.generer("chute", {"hauteur": 10}, ouvrir=False)
            b = kl3.generer("chute", {"hauteur": 20}, ouvrir=False)
        self.assertNotEqual(a, b)
        self.assertEqual(len(list(H.glob("*.html"))), 2)

    def test_whatsapp_message_sans_que(self):
        ks._H.setdefault("passe", "PASSE")
        ks.activer_reseau("whatsapp", True)
        class K:
            def __init__(self): self.questions = []
            def confirmer(self, q): self.questions.append(q); return False
        k = K()
        with mock.patch.object(ks, "trouver_contact", return_value=("marc", "+237677123456")):
            ks.cmd_whatsapp(k, "whatsapp à marc dis lui que je suis en route")
        self.assertIn("« je suis en route »", k.questions[0])

    def test_pendule_180_sans_erreur(self):
        exacte, simple = kl.periode_pendule(1.0, 180)
        self.assertGreater(exacte, 10)

    def test_application_non_executable_refusee_sous_linux(self):
        if sys.platform == "win32":
            self.skipTest("regle propre a Linux")
        f = Path(tempfile.mkdtemp()) / "pasexec"
        f.write_text("x")
        f.chmod(0o644)
        self.assertIn("exécutable", ka.ajouter_perso("Test", str(f)))


class TestCorrectionsRevue(Base):
    def setUp(self):
        super().setUp()
        self.K = _moteur_pret()

    # 1. Synthese vocale
    def test_nombres_lus_a_la_francaise(self):
        import kitt_complet as K
        self.assertEqual(K.vers_parole("Pendule : 2.5 secondes, adresse 127.0.0.1, et 3.14"),
                         "Pendule : 2,5 secondes, adresse 127.0.0.1, et 3,14")

    def test_erreur_voix_signalee_une_fois(self):
        class MoteurCasse:
            def say(self, texte): raise RuntimeError("pilote absent")
            def runAndWait(self): pass
        import kitt_complet as K
        voix = K.Voix.__new__(K.Voix)
        voix.moteur = MoteurCasse()
        k = K.Kitt(None)
        k.voix = voix
        k.parler("Premier message")
        k.parler("Deuxième message")
        journal = k.mem.exe("SELECT resultat FROM journal WHERE module = 'voix'")
        self.assertEqual(len(journal), 1)
        self.assertIn("pilote absent", journal[0][0])

    # 2. Limite WhatsApp persistante, fermee en cas d'echec
    def test_limite_survit_au_redemarrage(self):
        fichier = Path(tempfile.mkdtemp()) / "limite.json"
        a = sec.Limiteur(2, fichier)
        self.assertTrue(a.autorise()); self.assertTrue(a.autorise())
        b = sec.Limiteur(2, fichier)          # nouvelle instance : comme apres un redemarrage
        self.assertFalse(b.autorise())

    def test_limite_fermee_si_sauvegarde_impossible(self):
        base = Path(tempfile.mkdtemp())
        bloque = base / "fichier"
        bloque.write_text("x")
        lim = sec.Limiteur(5, bloque / "limite.json")   # le « dossier » est un fichier : echec
        self.assertFalse(lim.autorise())

    # 3. Cache des applications
    def test_menu_demarrer_pas_relu_a_chaque_commande(self):
        menu = self.dossier / "menu_cache"
        menu.mkdir()
        (menu / "Calc.lnk").write_text("x")
        appels = []
        original = ka._scanner
        def espion(d):
            appels.append(1)
            return original(d)
        with mock.patch.object(ka, "_scanner", side_effect=espion):
            ka._CACHE.clear()
            ka.decouvrir([menu]); ka.decouvrir([menu]); ka.decouvrir([menu])
        self.assertEqual(len(appels), 1)

    # 4. Recettes : une modification remplace les anciens declencheurs
    def test_modification_remplace_les_declencheurs(self):
        ks.creer_recette("salut_rev", ["bonjour"], "Salut A")
        ks.creer_recette("salut_rev", ["coucou"], "Salut B")
        K = self.K
        decl = [d for n, dd, _f in K.SKILLS if n == "salut_rev" for d in dd]
        self.assertEqual(decl, [K.sans_accents("coucou")])
        self.assertFalse(any(K.correspond(d, K.sans_accents("bonjour"))
                             for n, dd, _f in K.SKILLS if n == "salut_rev" for d in dd))

    def test_suppression_debranche_la_recette(self):
        ks.creer_recette("salut_sup", ["hello test"], "Hi")
        ks.desinstaller("salut_sup")
        self.assertFalse(any(n == "salut_sup" for n, _d, _f in self.K.SKILLS))

    # 5. Code mort
    def test_classe_interface_supprimee(self):
        import kitt_complet as K
        self.assertFalse(hasattr(K, "Interface"))
        self.assertTrue(hasattr(K, "boucle_gestes"))


class TestSixPoints(Base):
    """Verifie les six points de la revue : voix, WhatsApp persistant, decimales, cache, recettes, code mort."""

    def test_erreur_de_synthese_signalee_pas_avalee(self):
        import kitt_complet as K
        voix = K.Voix(lambda m: None)
        voix.moteur = mock.Mock()
        voix.moteur.say.side_effect = RuntimeError("moteur absent")
        voix.dire("bonjour")
        self.assertEqual(voix.erreur_voix, "moteur absent")

    def test_limite_whatsapp_survit_au_redemarrage(self):
        f = self.dossier / "limite.json"
        a = sec.Limiteur(2, f)
        self.assertTrue(a.autorise())
        self.assertTrue(a.autorise())
        b = sec.Limiteur(2, f)           # nouveau processus : le compteur est repris du fichier
        self.assertFalse(b.autorise())

    def test_decimales_francaises_dans_le_journal_et_la_voix(self):
        import kitt_complet as K
        self.assertEqual(K.vers_parole("pH égal à 2.00 et 0.01"), "pH égal à 2,00 et 0,01")
        self.assertEqual(K.vers_parole("adresse 127.0.0.1"), "adresse 127.0.0.1")

    def test_cache_des_applications(self):
        import kitt_applications as ka2
        ka2._CACHE.clear()
        d = Path(tempfile.mkdtemp())
        (d / "Calc.lnk").write_text("x")
        premier = ka2.decouvrir([d])
        (d / "Nouveau.lnk").write_text("x")
        self.assertEqual(ka2.decouvrir([d]), premier)     # encore dans le cache : pas relu
        ka2._CACHE.clear()
        self.assertIn("nouveau", ka2.decouvrir([d]))       # cache vide : relu

    def test_recette_modifiee_remplace_les_anciens_declencheurs(self):
        import kitt_complet as K
        ks.enregistrer(K.skill, K.PASSE, K.SKILLS)
        ks.creer_recette("salut_test", ["bonjour test"], "Salut A")
        ks.creer_recette("salut_test", ["coucou test"], "Salut B")
        norm = K.sans_accents
        tous = [(nom, d) for nom, decl, _f in K.SKILLS for d in decl if nom == "salut_test"]
        self.assertTrue(any(K.correspond(d, norm("coucou test")) for _n, d in tous))
        self.assertFalse(any(K.correspond(d, norm("bonjour test")) for _n, d in tous))

    def test_code_mort_retire(self):
        import kitt_complet as K
        self.assertFalse(hasattr(K, "Interface"))


class TestPointsRevus(unittest.TestCase):
    """Verrouille les corrections verifiees lors de la seconde revue."""

    @classmethod
    def setUpClass(cls):
        import kitt_complet as K
        cls.K = K

    def test_recette_modifiee_ancien_declencheur_inactif(self):
        K = self.K
        if not getattr(TestPointsRevus, "_pret", False):
            ks.enregistrer(K.skill, K.PASSE, K.SKILLS)
            TestPointsRevus._pret = True
        k = K.Kitt(None)
        k.traiter("crée skill rev_test | ancien revision | Réponse A")
        k.traiter("crée skill rev_test | nouveau revision | Réponse B")
        self.assertIsNone(k.traiter("ancien revision"))           # ne doit pas repondre
        self.assertIsNone(k.traiter("nouveau revision"))
        self.assertTrue(any(e[0] == "rev_test" for e in K.SKILLS))
        ks.desinstaller("rev_test")
        self.assertFalse(any(e[0] == "rev_test" for e in K.SKILLS))

    def test_limiteur_survit_au_redemarrage(self):
        f = Path(tempfile.mkdtemp()) / "limite.json"
        a = sec.Limiteur(2, f)
        self.assertTrue(a.autorise())
        self.assertTrue(a.autorise())
        b = sec.Limiteur(2, f)                 # « redemarrage » : nouvelle instance
        self.assertFalse(b.autorise())

    def test_cache_des_applications(self):
        with mock.patch.object(ka, "_scanner", return_value={"x": ("X", "/x")}) as scan:
            d = [Path(tempfile.mkdtemp())]
            ka.decouvrir(d)
            ka.decouvrir(d)
        self.assertEqual(scan.call_count, 1)

    def test_avertissement_voix_une_fois_et_journal(self):
        K = self.K
        class Moteur:
            def say(self, t): pass
            def runAndWait(self): raise RuntimeError("pilote absent")
        k = K.Kitt(None)
        avant = len(k.mem.exe("SELECT 1 FROM journal WHERE module = 'voix'"))   # base partagee : on compte l'ajout
        k.voix = K.Voix(lambda *a: None)
        k.voix.moteur = Moteur()
        k.parler("Un message.")
        k.parler("Un autre message.")
        apres = len(k.mem.exe("SELECT 1 FROM journal WHERE module = 'voix'"))
        self.assertEqual(apres - avant, 1)

    def test_decimal_lu_avec_virgule(self):
        self.assertEqual(self.K.vers_parole("Le pendule dure 2.637 secondes"), "Le pendule dure 2,637 secondes")
        self.assertEqual(self.K.vers_parole("Adresse 127.0.0.1"), "Adresse 127.0.0.1")

    def test_plus_d_interface_orpheline(self):
        self.assertFalse(hasattr(self.K, "Interface"))


class TestTonEtDiscussion(Base):
    def test_ton_par_defaut_et_valeurs_invalides(self):
        self.assertEqual(sec.charger_config()["ton"], "chaleureux")
        sec.CONFIG.write_text(json.dumps({"ton": "bizarre"}), encoding="utf-8")
        self.assertEqual(sec.charger_config()["ton"], "chaleureux")
        sec.CONFIG.write_text(json.dumps({"ton": "sobre"}), encoding="utf-8")
        self.assertEqual(sec.charger_config()["ton"], "sobre")

    def test_sobre_utilise_la_formulation_de_base(self):
        sec.CONFIG.write_text(json.dumps({"ton": "sobre"}), encoding="utf-8")
        for _ in range(30):
            self.assertIn(ton.phrase("confirme"), ton.PHRASES["confirme"])

    def test_chaleureux_utilise_la_variante(self):
        sec.CONFIG.write_text(json.dumps({"ton": "chaleureux"}), encoding="utf-8")
        for _ in range(30):
            self.assertIn(ton.phrase("confirme"), ton.PHRASES["confirme_chaleureux"])

    def test_messages_avec_proposition(self):
        rep = ton.phrase("app_introuvable", nom="photoshop")
        self.assertIn("photoshop", rep)
        self.assertNotIn("{", rep)

    def test_confirmation_suit_le_ton(self):
        import kitt_complet as K
        sec.CONFIG.write_text(json.dumps({"ton": "chaleureux"}), encoding="utf-8")
        k = K.Kitt(None)
        k.texte_q.put("oui")
        dits = []
        with mock.patch.object(K.Kitt, "parler", lambda self, t, memoriser=True: dits.append(t)):
            self.assertTrue(k.confirmer("J'efface le contact Marc"))
        self.assertTrue(dits[0].startswith("J'efface le contact Marc "))
        self.assertIn(dits[0][len("J'efface le contact Marc "):], ton.PHRASES["confirme_chaleureux"])

    def test_temperature_discussion_transmise(self):
        import kitt_complet as K
        import kitt_fiabilite as F
        capture = {}
        orig = K._appeler
        def faux(systeme, consigne, modele, max_tokens, delai, images, temperature=None):
            capture["t"] = temperature
            return "Bonjour, je vous écoute."
        K._appeler = faux
        try:
            K.generer("Sys", "Salut", temperature=F.TEMPERATURE_DISCUSSION)
        finally:
            K._appeler = orig
        self.assertEqual(capture["t"], 0.7)

    def test_options_envoyees_au_modele(self):
        import kitt_complet as K
        import kitt_fiabilite as F
        envoye = {}
        class Reponse:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b'{"response": "Bonjour"}'
        class Ouvreur:
            def open(self, req, timeout=None):
                envoye["corps"] = json.loads(req.data.decode("utf-8"))
                return Reponse()
        with mock.patch.object(K.urllib.request, "build_opener", return_value=Ouvreur()):
            K._appeler("Sys", "Salut", "m", None, 10, None, None)
        self.assertEqual(envoye["corps"]["options"]["temperature"], F.TEMPERATURE)
        with mock.patch.object(K.urllib.request, "build_opener", return_value=Ouvreur()):
            K._appeler("Sys", "Salut", "m", None, 10, None, 0.7)
        self.assertEqual(envoye["corps"]["options"]["temperature"], 0.7)


class TestIdeesEtAvis(unittest.TestCase):
    def setUp(self):
        self.recu = []
        def faux(systeme, consigne, **kw):
            self.recu.append((systeme, consigne, kw))
            return "Réponse simulée."
        kid.configurer(faux)

    def tearDown(self):
        kid.configurer(None)

    def test_sujets_sensibles_detectes(self):
        self.assertTrue(kid.est_sensible("le président du pays"))
        self.assertTrue(kid.est_sensible("un médicament contre la migraine"))
        self.assertTrue(kid.est_sensible("investir en bourse"))
        self.assertFalse(kid.est_sensible("un cadeau d'anniversaire"))

    def test_idees_extrait_le_sujet_et_demande_des_pistes(self):
        rep = kid.idees("donne-moi des idées pour un cadeau d'anniversaire",
                        ["donne moi des idees", "donne-moi des idees", "idees pour", "des idees"])
        self.assertEqual(rep, "Réponse simulée.")
        systeme, consigne, kw = self.recu[0]
        self.assertIn("cadeau d'anniversaire", consigne)
        self.assertEqual(systeme, kid.SYSTEME_IDEES)
        self.assertEqual(kw["temperature"], 0.7)

    def test_avis_motive_hors_sujet_sensible(self):
        kid.avis("que penses-tu de Linux pour un vieil ordinateur", ["que penses-tu", "ton avis"])
        self.assertEqual(self.recu[0][0], kid.SYSTEME_AVIS)

    def test_avis_sensible_sans_prise_de_parti(self):
        kid.avis("que penses-tu du président actuel", ["que penses-tu"])
        self.assertEqual(self.recu[0][0], kid.SYSTEME_SENSIBLE)

    def test_sans_sujet_demande_de_preciser(self):
        self.assertIn("Sur quel sujet", kid.idees("donne-moi des idées", ["donne-moi des idees"]))

    def test_idee_spontanee_contextuelle(self):
        self.assertIn("tâche la plus courte", kid.idee_spontanee({"taches": 6}, "Michael"))
        self.assertIn("sauvegarde", kid.idee_spontanee({"batterie": (20, False)}, "Michael"))

    def test_idee_spontanee_au_plus_une_fois_par_jour(self):
        from datetime import datetime, timedelta
        ini = ki.Initiatives()
        t0 = datetime(2026, 10, 9, 14, 0)
        ini.activite(t0)
        premier = [c for c, _ in ini.decider(t0, {}, "M", idees=True)]
        self.assertEqual(premier, ["idee"])
        ini.annoncer("idee", t0)
        ini.activite(t0 + timedelta(hours=1))
        self.assertEqual([c for c, _ in ini.decider(t0 + timedelta(hours=1), {}, "M", idees=True)], [])
        ini.activite(t0 + timedelta(hours=25))
        self.assertEqual([c for c, _ in ini.decider(t0 + timedelta(hours=25), {}, "M", idees=True)], ["idee"])

    def test_idee_spontanee_desactivable(self):
        from datetime import datetime, timedelta
        ini = ki.Initiatives()
        t0 = datetime(2026, 10, 9, 14, 0)
        ini.activite(t0)
        self.assertEqual(ini.decider(t0, {}, "M", idees=False), [])

    def test_commande_desactive_les_idees_seulement(self):
        ks.cmd_initiatives(Stub(), "desactive les idées")
        cfg = sec.charger_config()
        self.assertFalse(cfg["idees_spontanees"])
        self.assertTrue(cfg["initiatives"]["activees"])
        ks.cmd_initiatives(Stub(), "active les idées")
        self.assertTrue(sec.charger_config()["idees_spontanees"])

    def test_sans_modele_message_clair(self):
        kid.configurer(None)
        self.assertIn("pas configuré", kid.avis("que penses-tu de Linux", ["que penses-tu"]))


class TestRevueComplete(Base):
    @classmethod
    def setUpClass(cls):
        import kitt_complet as K
        cls.K = K

    def test_aucun_shell_dans_le_code(self):
        source = (Path(__file__).parent / "kitt_complet.py").read_text(encoding="utf-8")
        self.assertNotIn("shell=True", source)

    def test_positions_avec_accents_decomposes(self):
        K = self.K
        decompose = unicodedata.normalize("NFD", "donne-moi des idées pour un cadeau")
        self.assertEqual(K.apres(decompose, ["pour"]).strip(), "un cadeau")

    def test_sujet_idees_avec_accents_decomposes(self):
        import unicodedata as u
        texte = u.normalize("NFD", "donne-moi des idées pour un cadeau")
        self.assertEqual(kid._sujet(texte, ["donne moi des idees", "idees pour"]), "un cadeau")

    def test_sauvegarde_base_coherente(self):
        import sqlite3 as sq
        K = self.K
        k = K.Kitt(None)
        k.mem.exe("INSERT OR REPLACE INTO contacts VALUES ('Test Sauvegarde', NULL)")
        dossier = Path(tempfile.mkdtemp())
        K.SAUVEGARDES = dossier
        chemin, _n, _c = K.sauvegarder(k.mem)
        with zipfile.ZipFile(chemin) as z:
            z.extract("kitt.db", dossier / "verif")
        con = sq.connect(dossier / "verif" / "kitt.db")
        noms = [r[0] for r in con.execute("SELECT nom FROM contacts")]
        con.close()
        self.assertIn("Test Sauvegarde", noms)
        self.assertFalse((dossier / "kitt_base_copie.db").exists())

    def test_ecriture_atomique_sans_fichier_residuel(self):
        f = Path(tempfile.mkdtemp()) / "config.json"
        sec.ecrire_prive(f, '{"a": 1}')
        self.assertEqual(f.read_text(encoding="utf-8"), '{"a": 1}')
        self.assertFalse(f.with_name(f.name + ".tmp").exists())

    def test_ouverture_echouee_signalee(self):
        """Si le programme qui ouvre les fichiers est absent, la fonction le signale (False)."""
        if sys.platform == "win32":
            self.skipTest("regle propre a Linux/macOS")
        with mock.patch.object(self.K.subprocess, "Popen", side_effect=FileNotFoundError("xdg-open")):
            self.assertFalse(self.K.ouvrir_fichier(Path("/tmp/zz.md")))


class TestInterfaceNavigateur(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import kitt_complet as K
        cls.K = K
        cls.ui = kw.InterfaceWeb(port=0)
        cls.k = K.Kitt(cls.ui)
        cls.ui.kitt = cls.k
        cls.ui._demarrer_serveur()
        threading.Thread(target=cls.ui.serveur.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.ui.port}"

    @classmethod
    def tearDownClass(cls):
        cls.ui.serveur.shutdown()
        cls.ui.serveur.server_close()

    def _req(self, chemin, jeton=None, corps=None, hote=None, origine=None):
        data = json.dumps(corps).encode("utf-8") if corps is not None else None
        r = urllib.request.Request(self.base + chemin, data=data, method="POST" if corps is not None else "GET")
        if jeton:
            r.add_header("X-Kitt-Jeton", jeton)
        if corps is not None:
            r.add_header("Content-Type", "application/json")
            r.add_header("Origin", origine or self.base)
        if hote:
            r.add_header("Host", hote)
        try:
            with urllib.request.urlopen(r, timeout=5) as rep:
                return rep.status, rep.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_ecoute_uniquement_sur_localhost(self):
        self.assertEqual(self.ui.serveur.server_address[0], "127.0.0.1")
        self.assertNotEqual(kw.HOTE, "0.0.0.0")

    def test_page_exige_le_jeton(self):
        self.assertEqual(self._req("/")[0], 403)
        self.assertEqual(self._req("/?jeton=faux")[0], 403)
        self.assertEqual(self._req("/?jeton=" + self.ui.jeton)[0], 200)

    def test_api_exige_le_jeton(self):
        self.assertEqual(self._req("/api/etat")[0], 403)
        self.assertEqual(self._req("/api/etat", self.ui.jeton)[0], 200)

    def test_commande_refusee_sans_jeton_ou_origine_etrangere(self):
        self.assertEqual(self._req("/api/commande", None, {"texte": "x"})[0], 403)
        self.assertEqual(self._req("/api/commande", self.ui.jeton, {"texte": "x"},
                                   origine="http://evil.example")[0], 403)

    def test_nom_d_hote_inconnu_refuse(self):
        self.assertEqual(self._req("/?jeton=" + self.ui.jeton, hote="evil.example")[0], 403)
        self.assertEqual(self._req("/api/etat", self.ui.jeton, hote="evil.example")[0], 403)

    def test_commande_valide_arrive_dans_kitt(self):
        avant = self.k.texte_q.qsize()
        code, _ = self._req("/api/commande", self.ui.jeton, {"texte": "quelle heure est-il"})
        self.assertEqual(code, 200)
        self.assertEqual(self.k.texte_q.qsize(), avant + 1)
        self.k.texte_q.get_nowait()

    def test_fichier_inexistant_refuse(self):
        code, _ = self._req("/api/fichier", self.ui.jeton, {"chemin": "/chemin/absent/zz.txt"},)
        self.assertEqual(code, 400)

    def test_fichier_existant_joint(self):
        f = Path(tempfile.mkdtemp()) / "note.txt"
        f.write_text("bonjour", encoding="utf-8")
        code, _ = self._req("/api/fichier", self.ui.jeton, {"chemin": str(f)})
        self.assertEqual(code, 200)
        self.assertEqual(self.k.fichier_courant, f)
        self.k.texte_q.get_nowait()

    def test_journal_incremental(self):
        self.ui.log("premiere ligne")
        self.ui.log("seconde ligne")
        code, corps = self._req("/api/etat?depuis=0", self.ui.jeton)
        donnees = json.loads(corps)
        textes = [t for _n, t in donnees["lignes"]]
        self.assertIn("seconde ligne", textes)
        dernier = max(n for n, _ in donnees["lignes"])
        code, corps = self._req(f"/api/etat?depuis={dernier}", self.ui.jeton)
        self.assertEqual(json.loads(corps)["lignes"], [])

    def test_bandeau_de_demarrage(self):
        self.ui.url = f"http://localhost:{self.ui.port}/?jeton={self.ui.jeton}"
        texte = self.ui.bandeau()
        self.assertIn(str(self.ui.port), texte)
        self.assertIn("127.0.0.1", texte)
        self.assertIn("ce PC", texte)
        self.assertIn("au revoir", texte)
        self.assertIn(self.ui.jeton, texte)

    def test_infos_serveur_dans_l_etat(self):
        code, corps = self._req("/api/etat", self.ui.jeton)
        infos = json.loads(corps)["serveur"]
        self.assertEqual(infos["hote"], "127.0.0.1")
        self.assertEqual(infos["port"], self.ui.port)
        self.assertIsNotNone(infos["demarre"])

    def test_port_occupe_signale(self):
        import socket
        occupe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        occupe.bind(("127.0.0.1", 0))
        occupe.listen(1)
        port_occupe = occupe.getsockname()[1]
        try:
            ui = kw.InterfaceWeb(port=port_occupe)
            with self.assertRaises(OSError):
                ui._demarrer_serveur()
            self.assertEqual(ui.ports_occupes, [port_occupe])
        finally:
            occupe.close()

    def test_texte_affiche_jamais_en_html(self):
        self.assertNotIn("innerHTML", kw.PAGE)
        self.assertIn("textContent", kw.PAGE)


class TestAvertissementsConfig(Base):
    def setUp(self):
        super().setUp()
        sec.AVERTISSEMENTS.clear()

    def test_config_valide_sans_avertissement(self):
        sec.CONFIG.write_text(json.dumps({"prenom": "Michael", "ton": "sobre"}), encoding="utf-8")
        sec.charger_config()
        self.assertEqual(sec.avertissements(), [])

    def test_valeur_invalide_signalee(self):
        sec.CONFIG.write_text(json.dumps({"ton": "bizarre", "idees_spontanees": "oui"}), encoding="utf-8")
        sec.charger_config()
        textes = " ".join(sec.avertissements())
        self.assertIn("« ton »", textes)
        self.assertIn("« idees_spontanees »", textes)

    def test_faute_de_frappe_signalee(self):
        sec.CONFIG.write_text(json.dumps({"tom": "sobre"}), encoding="utf-8")
        sec.charger_config()
        self.assertTrue(any("« tom »" in a for a in sec.avertissements()))

    def test_json_invalide_signale(self):
        sec.CONFIG.write_text("{ pas du json", encoding="utf-8")
        cfg = sec.charger_config()
        self.assertEqual(cfg["ton"], "chaleureux")
        self.assertTrue(any("lisible" in a for a in sec.avertissements()))

    def test_pas_de_doublon(self):
        sec.CONFIG.write_text(json.dumps({"ton": "bizarre"}), encoding="utf-8")
        for _ in range(5):
            sec.charger_config()
        self.assertEqual(len(sec.avertissements()), 1)

    def test_fichier_absent_normal(self):
        sec.charger_config()
        self.assertEqual(sec.avertissements(), [])

    def test_cache_suit_les_modifications(self):
        """Meme taille, valeur differente : la modification doit etre vue tout de suite."""
        sec.CONFIG.write_text(json.dumps({"ton": "sobre"}), encoding="utf-8")
        self.assertEqual(sec.charger_config()["ton"], "sobre")
        sec.CONFIG.write_text(json.dumps({"ton": "espiegle"}), encoding="utf-8")
        self.assertEqual(sec.charger_config()["ton"], "espiegle")
        sec.CONFIG.write_text(json.dumps({"ton": "sobre"}), encoding="utf-8")
        self.assertEqual(sec.charger_config()["ton"], "sobre")

    def test_cache_renvoie_des_copies(self):
        sec.CONFIG.write_text(json.dumps({"ton": "sobre"}), encoding="utf-8")
        cfg = sec.charger_config()
        cfg["ton"] = "modifié à la main"
        self.assertEqual(sec.charger_config()["ton"], "sobre")


class TestEntrees(Base):
    def test_choix_par_defaut_et_options(self):
        par_defaut = {"voix": True, "gestes": False}
        self.assertEqual(sec.choisir_entrees(["kitt_complet.py"], par_defaut), {"voix": True, "gestes": False})
        self.assertEqual(sec.choisir_entrees(["x", "--gestes"], par_defaut), {"voix": True, "gestes": True})
        self.assertEqual(sec.choisir_entrees(["x", "--sans-voix"], par_defaut), {"voix": False, "gestes": False})
        self.assertEqual(sec.choisir_entrees(["x", "--gestes", "--sans-gestes"], par_defaut)["gestes"], False)

    def test_configuration_entrees_sanitisee(self):
        self.assertEqual(sec.charger_config()["entrees"], {"voix": True, "gestes": False})
        sec.CONFIG.write_text(json.dumps({"entrees": {"voix": "oui", "gestes": True}}), encoding="utf-8")
        cfg = sec.charger_config()["entrees"]
        self.assertTrue(cfg["voix"])          # valeur non booleenne : par defaut
        self.assertTrue(cfg["gestes"])

    def test_gestes_sans_bibliotheques_refuses(self):
        import kitt_complet as K
        if K.cv2 is not None and K.mp is not None:
            self.skipTest("bibliotheques de gestes installees")
        k = K.Kitt(None)
        rep = k.regler_entree("gestes", True)
        self.assertIn("opencv-python", rep)
        self.assertFalse(k.gestes_actifs)

    def test_voix_absente_refusee(self):
        import kitt_complet as K
        k = K.Kitt(None)
        self.assertIsNone(k.voix)
        self.assertIn("pas disponible", k.regler_entree("voix", True))
        self.assertFalse(k.voix_active)

    def test_voix_coupee_n_ecoute_plus_le_micro(self):
        import kitt_complet as K
        class MicoFaux:
            mic = True
            rec_reveil = None
            def ecouter(self, *a, **k):
                raise AssertionError("le micro ne doit pas etre ecoute")
        k = K.Kitt(None)
        k.voix = MicoFaux()
        k.voix_active = False
        k.ecouter(0.2)                            # ne doit pas lever d'erreur ni appeler le micro

    def test_voix_choisie_reste_active_au_demarrage(self):
        """Regression : le micro n'existe pas encore au moment de appliquer_entrees (il est cree dans boucle)."""
        import kitt_complet as K
        k = K.Kitt(None)
        self.assertIsNone(k.voix)
        K.appliquer_entrees(k, {"voix": True, "gestes": False})
        self.assertTrue(k.voix_active)
        K.appliquer_entrees(k, {"voix": False, "gestes": False})
        self.assertFalse(k.voix_active)

    def test_demarrage_ne_modifie_pas_la_configuration(self):
        """Le choix fait au demarrage ne vaut que pour la session (README)."""
        import kitt_complet as K
        sec.sauver_config(sec.charger_config())
        avant = sec.CONFIG.read_text(encoding="utf-8")
        k = K.Kitt(None)
        K.appliquer_entrees(k, {"voix": False, "gestes": False})
        self.assertEqual(sec.CONFIG.read_text(encoding="utf-8"), avant)

    def test_commande_vocale_enregistre_le_choix(self):
        import kitt_complet as K
        k = K.Kitt(None)
        k.regler_entree("voix", False)            # commande vocale : persiste
        self.assertFalse(sec.charger_config()["entrees"]["voix"])

    def test_commande_vocale_entrees(self):
        class K2:
            def __init__(self): self.appels = []
            def regler_entree(self, nom, actif):
                self.appels.append((nom, actif)); return "ok"
        k = K2()
        ks.cmd_entrees(k, "desactive la voix")
        ks.cmd_entrees(k, "active les gestes")
        self.assertEqual(k.appels, [("voix", False), ("gestes", True)])

    def test_boucle_gestes_sans_bibliotheque_se_termine(self):
        import kitt_complet as K
        if K.cv2 is not None and K.mp is not None:
            self.skipTest("bibliotheques de gestes installees")
        class KF: actif = True; gestes_actifs = False
        K.boucle_gestes(KF())   # doit revenir tout de suite, sans ouvrir de camera


class _Repere:
    def __init__(self, x, y):
        self.x, self.y = x, y


def _main(doigts, pouce_lateral=False, pouce_vertical=None, pouce_touche_index=False):
    """21 repères MediaPipe synthétiques. doigts : [index, majeur, annulaire, auriculaire] levés ou non."""
    lm = [_Repere(0.5, 0.6) for _ in range(21)]
    lm[0] = _Repere(0.5, 0.9)                              # poignet
    for (tip, pip), leve in zip(((8, 6), (12, 10), (16, 14), (20, 18)), doigts):
        lm[tip] = _Repere(0.5, 0.3 if leve else 0.6)
        lm[pip] = _Repere(0.5, 0.5)
    lm[3] = _Repere(0.5, 0.55)
    lm[17] = _Repere(0.7, 0.6)
    lm[4] = _Repere(0.2 if pouce_lateral else 0.68, 0.6)
    lm[5] = _Repere(0.5, 0.6)
    if pouce_vertical == "haut":
        lm[4] = _Repere(0.68, 0.3)
    elif pouce_vertical == "bas":
        lm[4] = _Repere(0.68, 0.9)
    if pouce_touche_index:
        lm[4] = _Repere(0.4, 0.4)
        lm[8] = _Repere(0.4, 0.4)
    return lm


class TestGestes(unittest.TestCase):
    def test_formes_reconnues(self):
        cas = {
            "paume": _main([True, True, True, True], pouce_lateral=True),
            "poing": _main([False, False, False, False]),
            "victoire": _main([True, True, False, False]),
            "pointer": _main([True, False, False, False]),
            "pistolet": _main([True, False, False, False], pouce_lateral=True),
            "cornes": _main([True, False, False, True]),
            "shaka": _main([False, False, False, True], pouce_lateral=True),
            "trois": _main([True, True, True, False]),
            "pouce_haut": _main([False, False, False, False], pouce_vertical="haut"),
            "pouce_bas": _main([False, False, False, False], pouce_vertical="bas"),
            "ok": _main([False, True, True, True], pouce_touche_index=True),
        }
        for attendu, lm in cas.items():
            self.assertEqual(kg.reconnaitre(lm), attendu, attendu)

    def test_geste_inconnu_renvoie_none(self):
        self.assertIsNone(kg.reconnaitre(_main([False, True, False, False])))

    def test_chaque_geste_a_une_commande(self):
        self.assertEqual(set(kg.GESTES), {"paume", "victoire", "poing", "pointer", "pistolet", "pouce_haut",
                                           "pouce_bas", "ok", "cornes", "shaka", "trois", "quatre"})

    def test_aucun_geste_n_a_d_effet_externe(self):
        """Pas de message, appel, suppression, programme, Internet ni confirmation par geste."""
        interdits = ["envoie", "ferme", "supprime", "efface", "installe", "désinstalle", "appelle",
                     "whatsapp", "active", "désactive", "sauvegarde", "ouvre", "lance", "internet",
                     "oui", "non", "confirme", "joue", "ajoute", "crée"]
        for geste, commande in kg.GESTES.items():
            norm = sec.normaliser(commande)
            for mot in interdits:
                self.assertNotIn(sec.normaliser(mot), norm, f"{geste} : « {mot} » dans « {commande} »")

    def test_chaque_commande_declenche_une_fonction(self):
        import kitt_complet as K
        if not getattr(TestGestes, "_pret", False):
            ks.enregistrer(K.skill, K.PASSE, K.SKILLS)
            TestGestes._pret = True
        declencheurs = [d for _nom, decl, _fn in K.SKILLS for d in decl]
        rates = [(g, c) for g, c in kg.GESTES.items() if g != "paume"
                 and not any(K.correspond(d, K.sans_accents(c)) for d in declencheurs)]
        self.assertEqual(rates, [])


class TestLaboEtendu(Base):
    def test_ressort(self):
        import kitt_labo as kl
        self.assertAlmostEqual(kl.ressort_amorti(2, 50, 0)["periode"], 2 * math.pi * math.sqrt(2 / 50), places=6)
        self.assertIsNone(kl.ressort_amorti(1, 10, 100)["periode"])     # trop amorti : pas d'oscillation
        self.assertIsNone(kl.ressort_amorti(1, 10, 0)["demi_amplitude"])

    def test_circuit_rc(self):
        import kitt_labo as kl
        r = kl.circuit_rc(1000, 0.001, 5)
        self.assertAlmostEqual(r["tau"], 1.0)
        self.assertAlmostEqual(r["tension_a_tau"] / 5, 1 - math.exp(-1), places=6)

    def test_refraction_snell(self):
        import kitt_labo as kl
        self.assertAlmostEqual(kl.refraction(1.0, 1.333, 30), 22.03, places=2)
        self.assertIsNone(kl.refraction(1.333, 1.0, 60))                 # reflexion totale

    def test_conversions(self):
        import kitt_labo as kl
        self.assertAlmostEqual(kl.convertir(100, "km/h", "m/s"), 27.7778, places=3)
        self.assertAlmostEqual(kl.convertir(100, "c", "f"), 212.0)
        self.assertAlmostEqual(kl.convertir(0, "k", "c"), -273.15)
        with self.assertRaises(ValueError):
            kl.convertir(1, "km", "kg")

    def test_energie_pendule_conservee(self):
        import kitt_labo as kl
        t, ec, ep = kl.energie_pendule(1.0, 60)
        totales = [a + b for a, b in zip(ec, ep)]
        self.assertAlmostEqual(min(totales), max(totales), places=3)

    def test_commandes_physique(self):
        class K:
            def confirmer(self, q): return True
        self.assertIn("1,258", ks.cmd_physique(K(), "laboratoire ressort masse 2 raideur 50 amortissement 1"))
        self.assertIn("63 %", ks.cmd_physique(K(), "laboratoire circuit 1000 0,001 5"))
        self.assertIn("Réflexion totale", ks.cmd_physique(K(), "laboratoire réfraction 60 degrés eau air"))
        self.assertIn("°F", ks.cmd_physique(K(), "convertis 100 C en F"))

    def test_geste_quatre(self):
        import kitt_gestes as kg2
        lm = _main([True, True, True, True], pouce_lateral=False)
        self.assertEqual(kg2.reconnaitre(lm), "quatre")
        self.assertEqual(kg2.GESTES["quatre"], "kitt propose labo pendule")

    def test_proposition_exige_confirmation(self):
        appels = []
        class K:
            def confirmer(self, q):
                appels.append(q); return False
        ks._H.setdefault("passe", "PASSE")
        rep = ks.cmd_labo3d(K(), "kitt propose labo pendule")
        self.assertEqual(len(appels), 1)
        self.assertIn(rep, ton.PHRASES["annule"])

    def test_tir_compare_avec_et_sans_air(self):
        d = kl3b.construire("tir", {"vitesse": 40, "angle": 45})
        noms = [s_["nom"] for s_ in d["series"]]
        self.assertEqual(noms, ["avec l'air", "sans air"])
        avec, sans = d["series"]
        self.assertGreater(len(sans["points"]), 0)

    def test_pendule_a_un_graphique_d_energie(self):
        d = kl3b.construire("pendule", {"longueur": 1.0, "angle": 60})
        self.assertIsNotNone(d["graphe"])
        self.assertEqual([s_["nom"] for s_ in d["graphe"]["series"]], ["cinétique", "potentielle", "totale"])


class TestRevueLaboratoire(Base):
    @classmethod
    def setUpClass(cls):
        import kitt_complet as K
        cls.K = K
        ks.enregistrer(K.skill, K.PASSE, K.SKILLS) if not getattr(TestRevueLaboratoire, "_pret", False) else None
        TestRevueLaboratoire._pret = True

    def test_ressort_sans_chiffres_demande_les_valeurs(self):
        class C:
            def confirmer(self, q): return True
        self.assertIn("Donnez", ks.cmd_physique(C(), "laboratoire ressort"))

    def test_convertir_hors_labo_laisse_la_main(self):
        class C:
            def confirmer(self, q): return True
        self.assertIs(ks.cmd_physique(C(), "convertir un fichier pdf en word"), self.K.PASSE)

    def test_unites_francaises_acceptees(self):
        import kitt_labo as kl
        self.assertAlmostEqual(kl.convertir(5, "pieds", "mètres".replace("è", "e")), 1.524, places=3)
        self.assertAlmostEqual(kl.convertir(2, "litres", "ml"), 2000.0)

    def test_affichage_unite_canonique(self):
        class C:
            def confirmer(self, q): return True
        self.assertIn("= 1,524 m.", ks.cmd_physique(C(), "convertis 5 pieds en mètres"))


if __name__ == "__main__":
    unittest.main()
