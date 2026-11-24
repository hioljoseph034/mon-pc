"""Fiabilite des reponses du modele local : nettoyage, langue, passages pertinents.

Ces fonctions ne remplacent pas un bon modele. Elles limitent ce qui sort du modele :
- temperature basse, pour des reponses plus stables ;
- suppression des marqueurs internes (<|assistant|>, etc.) et des prefixes « KITT : » ;
- detection d'une reponse en anglais, avec une seule nouvelle tentative en francais ;
- pour un document long, seuls les passages contenant les mots de la question sont transmis.
"""
import re

import kitt_securite as sec

TEMPERATURE = 0.3                # reponses factuelles : stables
TEMPERATURE_DISCUSSION = 0.7     # conversation libre : plus de variete

_JETONS = re.compile(r"<\|[^|>]*\|>|</s>|<s>|\[/?INST\]")
_PREFIXE = re.compile(r"^\s*(KITT|Réponse|Reponse|Answer)\s*:\s*", re.IGNORECASE)
_MOTS_FR = set("le la les de des du un une et est sont que qui dans pour avec sur pas ce cette "
               "vous je il elle nous au aux en qu l d on ou".split())
_MOTS_EN = set("the and is are of to in that it for with on this you i he she we be have was not "
               "what which from by or".split())
_MOTS_VIDES = set("le la les de des du un une et ou est sont que qui quoi dans pour avec sur par ce "
                  "cet cette ces il elle on tu vous nous je mon ton son ma ta sa mes tes ses quel quelle "
                  "quels quelles quand comment combien pourquoi les aux".split())


def nettoyer(texte):
    """Retire les marqueurs internes du modele et les prefixes de role."""
    t = _JETONS.sub("", texte or "")
    t = _PREFIXE.sub("", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def est_francais(texte):
    """Vrai si le texte ressemble davantage au francais qu'a l'anglais. Un texte tres court est accepte."""
    mots = re.findall(r"[a-z]+", sec.normaliser(texte))
    if len(mots) < 4:
        return True
    fr = sum(m in _MOTS_FR for m in mots)
    en = sum(m in _MOTS_EN for m in mots)
    return en == 0 or fr >= en


def generer_verifie(produire, systeme, consigne):
    """`produire(systeme, consigne)` renvoie le texte brut du modele.
    Le texte est nettoye. S'il est en anglais, on tente une fois de plus en francais."""
    texte = nettoyer(produire(systeme, consigne))
    if texte and not est_francais(texte):
        essai = nettoyer(produire(systeme + " Réponds uniquement en français.", consigne))
        if essai and est_francais(essai):
            texte = essai
    return texte


def mots_cles(question):
    return {m for m in re.findall(r"[a-z]+", sec.normaliser(question)) if len(m) >= 3 and m not in _MOTS_VIDES}


def passages(texte, question, taille=700, n=3):
    """Les `n` passages du texte qui contiennent le plus de mots de la question, dans l'ordre du texte.
    Renvoie une liste vide si aucun passage ne correspond."""
    cles = mots_cles(question)
    if not cles or not texte:
        return []
    pas = taille // 2
    scores = []
    for ordre, debut in enumerate(range(0, len(texte), pas)):
        morceau = texte[debut:debut + taille]
        if not morceau.strip():
            continue
        commun = len(cles & set(re.findall(r"[a-z]+", sec.normaliser(morceau))))
        if commun:
            scores.append((commun, -ordre, morceau))
    scores.sort(reverse=True)
    choisis = sorted(scores[:n], key=lambda x: -x[1])
    return [m for _, _, m in choisis]


def score_reponse(reponse, doit_contenir, ne_doit_pas_contenir):
    """Verifie une reponse attendue : tous les mots de `doit_contenir` presents, aucun de `ne_doit_pas_contenir`."""
    r = sec.normaliser(reponse)
    return all(sec.normaliser(m) in r for m in doit_contenir) and \
        not any(sec.normaliser(m) in r for m in ne_doit_pas_contenir)


def evaluer(produire, cas):
    """Joue un jeu de questions. `produire(systeme, consigne)` renvoie le texte brut du modele.
    Renvoie (reussis, total, echecs) ; un echec est un tuple (question, reponse)."""
    echecs = []
    for c in cas:
        reponse = generer_verifie(produire, "Tu réponds brièvement, en français.", c["question"])
        if not score_reponse(reponse, c.get("doit", []), c.get("interdit", [])):
            echecs.append((c["question"], reponse))
    return len(cas) - len(echecs), len(cas), echecs


CAS_REFERENCE = [
    {"question": "Quelle est la capitale du Cameroun ? Réponds en un mot.", "doit": ["yaounde"]},
    {"question": "Combien font 7 fois 8 ?", "doit": ["56"]},
    {"question": "Quelle est la couleur du ciel par temps clair ?", "doit": ["bleu"], "interdit": ["sky", "blue"]},
    {"question": "Quel est le contraire de chaud ?", "doit": ["froid"]},
    {"question": "Combien de jours y a-t-il dans une semaine ?", "doit": ["sept"]},
    {"question": "Quel est le contraire de grand ?", "doit": ["petit"]},
]
