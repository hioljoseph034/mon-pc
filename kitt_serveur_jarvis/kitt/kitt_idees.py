"""Idees et avis de KITT.

- « donne-moi des idees pour ... » : trois a cinq pistes, avec un avantage et un inconvenient.
- « que penses-tu de ... » : un avis motive, present comme un point de vue, avec ce qui le ferait changer.
- Sur les sujets sensibles (politique, religion, sante, droit, finances) : pas de prise de parti.
  KITT presente les arguments de chaque position et renvoie vers un professionnel si besoin.
- Idee spontanee : rarement, KITT peut proposer une idee de lui-meme (une fois par jour au plus,
  a un moment calme). Ces idees sont des phrases fixes, relues et sures, pas des generations du modele.

Le modele local est appele par la fonction fournie par kitt_complet (configurer), pour eviter
les imports circulaires. Les textes produits passent par generer (nettoyage, verification du francais).
"""
import re
import unicodedata

import kitt_fiabilite as F

_generer = None

SENSIBLES = ["politique", "election", "president", "parti", "religion", "dieu", "avortement", "guerre",
             "sante", "medicament", "maladie", "symptome", "diagnostic", "medical", "avocat", "proces",
             "juridique", "impot", "investir", "bourse", "crypto", "placement", "credit", "loi"]

SYSTEME_IDEES = ("Tu proposes des idees en francais, concretes et variees. Donne trois a cinq pistes numerotees. "
                 "Pour chacune : une phrase, un avantage et un inconvenient. Pas de preambule.")
SYSTEME_AVIS = ("Tu donnes ton avis en francais, de facon honnete et motivee, en cinq phrases au plus. "
                "Commence par « Mon avis : ». Termine par une phrase qui dit ce qui te ferait changer d'avis.")
SYSTEME_SENSIBLE = ("Le sujet est sensible. Ne prends pas parti. Presente les arguments principaux de chaque "
                    "position en francais, en quelques phrases, puis conseille de consulter un professionnel "
                    "si la question est personnelle.")


def configurer(generer):
    """Fournit au module la fonction generer de kitt_complet."""
    global _generer
    _generer = generer


def _normaliser(texte):
    s = (texte or "").lower().replace("\u2019", "'")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def est_sensible(sujet):
    mots = set(re.findall(r"[a-z]+", _normaliser(sujet)))
    return any(m in mots for m in SENSIBLES)


def _sujet(texte, declencheurs):
    """Ce qui suit le declencheur : « donne-moi des idees pour une fete » -> « une fete »."""
    texte = unicodedata.normalize("NFC", texte or "")      # positions identiques dans le texte et sa version simplifiee
    s = texte
    for d in sorted(declencheurs, key=len, reverse=True):
        m = re.search(re.escape(d), _normaliser(texte))
        if m:
            s = texte[m.end():]
            break
    return s.strip(" ?!.:,'\"")


def _appel(systeme, consigne):
    if _generer is None:
        return "Je ne peux pas réfléchir à voix haute pour l'instant : le modèle local n'est pas configuré."
    try:
        return _generer(systeme, consigne, max_tokens=350, delai=180,
                        temperature=F.TEMPERATURE_DISCUSSION)
    except Exception as e:
        return str(e) or "Je n'ai pas pu réfléchir à cette question."


def idees(texte, declencheurs):
    sujet = _sujet(texte, declencheurs)
    if not sujet:
        return "Sur quel sujet voulez-vous des idées ? Par exemple : donne-moi des idées pour un cadeau."
    if est_sensible(sujet):
        return _appel(SYSTEME_SENSIBLE, f"Question : {sujet}")
    return _appel(SYSTEME_IDEES, f"Donne des idées pour : {sujet}")


def avis(texte, declencheurs):
    sujet = _sujet(texte, declencheurs)
    if not sujet:
        return "Sur quoi voulez-vous mon avis ? Par exemple : que penses-tu de Linux pour un ordinateur ancien ?"
    if est_sensible(sujet):
        return _appel(SYSTEME_SENSIBLE, f"Question : {sujet}")
    return _appel(SYSTEME_AVIS, f"Question : {sujet}")


# Idees spontanees : phrases fixes, adaptees au contexte, jamais generees par le modele.
def idee_spontanee(ctx, prenom):
    """Une idee utile selon le contexte, ou None. Ne propose jamais d'action a la place de l'utilisateur."""
    taches = ctx.get("taches", 0)
    batterie = ctx.get("batterie")
    if taches >= 5:
        return (f"Une idée, {prenom} : commencez par la tâche la plus courte, cela relance l'élan. "
                "Dites « mes tâches » si vous voulez les voir.")
    if batterie and batterie[0] <= 30 and not batterie[1]:
        return ("Une idée : pendant que la batterie baisse, c'est un bon moment pour sauvegarder vos fichiers. "
                "Dites « sauvegarde ».")
    return (f"Si vous manquez d'inspiration, {prenom}, dites « donne-moi des idées pour » suivi du sujet.")
