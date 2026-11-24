"""Tests de la recherche du labo (Wikipédia simulé : aucun accès réseau)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_TMP = tempfile.mkdtemp(prefix="kitt-test-recherche-")
os.environ["HOME"] = _TMP
os.environ["USERPROFILE"] = _TMP
sys.path.insert(0, str(Path(__file__).resolve().parent))

import kitt_recherche as kr  # noqa: E402
import kitt_securite as sec  # noqa: E402


class TestRecherche(unittest.TestCase):
    def setUp(self):
        sec.CONFIG.parent.mkdir(parents=True, exist_ok=True)
        sec.CONFIG.write_text(json.dumps({"reseau": {"labo_web": True}}), encoding="utf-8")
        sec._CACHE_CONFIG.update({"brut": None, "cfg": None})

    def test_sujet_extrait(self):
        self.assertEqual(kr.extraire_sujet("labo recherche effet Doppler"), "effet Doppler")
        self.assertEqual(kr.extraire_sujet("recherche sur internet : loi d'Ohm"), "loi d'Ohm")
        self.assertIsNone(kr.extraire_sujet("labo recherche"))

    def test_refus_si_non_autorise(self):
        sec.CONFIG.parent.mkdir(parents=True, exist_ok=True)
        sec.CONFIG.write_text(json.dumps({"reseau": {"labo_web": False}}), encoding="utf-8")
        sec._CACHE_CONFIG.update({"brut": None, "cfg": None})
        with self.assertRaises(kr.RechercheIndisponible):
            kr.rechercher("effet Doppler")

    def test_adresses_en_https_wikipedia_seulement(self):
        self.assertEqual(kr.adresse_page("fr", "Effet Doppler"),
                         "https://fr.wikipedia.org/wiki/Effet_Doppler")
        self.assertTrue(sec.url_autorisee("labo_web", kr._api("fr", {"action": "query"})))
        self.assertFalse(sec.url_autorisee("labo_web", "http://fr.wikipedia.org/w/api.php"))
        self.assertFalse(sec.url_autorisee("labo_web", "https://exemple.com/x"))

    def test_sources_et_reponse(self):
        def faux_json(service, url, timeout=8):
            if "list=search" in url:
                return {"query": {"search": [{"title": "Effet Doppler"}]}}
            return {"query": {"pages": [{"extract": "Changement de fréquence perçue d'une onde."}]}}
        captures = {}
        def faux_generer(systeme, consigne, max_tokens=None, delai=None):
            captures["consigne"] = consigne
            return "Le son paraît plus aigu quand la source s'approche. https://pirate.example/x"
        with mock.patch.object(sec, "requete_json", side_effect=faux_json):
            sources = kr.rechercher("effet Doppler")
            rep = kr.repondre("effet Doppler", sources, faux_generer)
        self.assertEqual(sources[0]["url"], "https://fr.wikipedia.org/wiki/Effet_Doppler")
        self.assertIn("<extrait", captures["consigne"])
        self.assertNotIn("pirate.example", rep)                      # adresse inventée retirée
        self.assertIn("Sources :\n- Effet Doppler : https://fr.wikipedia.org/wiki/Effet_Doppler", rep)

    def test_rien_trouve(self):
        with mock.patch.object(sec, "requete_json", return_value={"query": {"search": []}}):
            self.assertEqual(kr.rechercher("zzzz"), [])


if __name__ == "__main__":
    unittest.main()
