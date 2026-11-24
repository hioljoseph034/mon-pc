"""Gestes de la main (webcam, landmarks MediaPipe) et les commandes qu'ils déclenchent.

Règle de sécurité : un geste ne déclenche que des commandes de consultation (agenda, tâches,
heure, aide...). Aucun geste n'envoie de message, n'appelle, ne supprime, n'ouvre de programme,
n'active Internet, ni ne confirme une action. Une confirmation par geste serait trop facile à
déclencher par accident.

Repères MediaPipe : 0 poignet ; 2-4 pouce ; 5-8 index ; 9-12 majeur ; 13-16 annulaire ; 17-20 auriculaire.
Les images ont l'axe y vers le bas : un doigt levé a sa pointe plus haut (y plus petit) que sa jointure.
"""
import math

GESTES = {
    "paume": "kitt",                         # réveil de KITT
    "victoire": "kitt mon agenda",
    "poing": "kitt état du système",
    "pointer": "kitt mes tâches",            # un doigt levé
    "pistolet": "kitt aide",                 # pouce et index
    "pouce_haut": "kitt quelle heure est-il",
    "pouce_bas": "kitt mes habitudes",
    "ok": "kitt quelle date sommes-nous",    # pouce et index se touchent
    "cornes": "kitt mes minuteurs",
    "shaka": "kitt mes notes",               # pouce et auriculaire
    "trois": "kitt mes conversations",
    "quatre": "kitt propose labo pendule",   # propose seulement : la confirmation est vocale ou ecrite
}


def _doigts_leves(lm):
    """index, majeur, annulaire, auriculaire : pointe au-dessus de la jointure."""
    return [lm[t].y < lm[p].y for t, p in ((8, 6), (12, 10), (16, 14), (20, 18))]


def _pouce_ecarte(lm):
    """Pouce tendu sur le cote (meme critere que la version precedente)."""
    return abs(lm[4].x - lm[17].x) > abs(lm[3].x - lm[17].x)


def _distance(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def reconnaitre(lm):
    """Nom du geste d'une main, ou None. `lm` : les 21 repères (objets avec x et y)."""
    index, majeur, annulaire, auriculaire = _doigts_leves(lm)
    doigts = [index, majeur, annulaire, auriculaire]
    pouce = _pouce_ecarte(lm)
    # Le pouce est tendu vers le haut ou le bas : pointe nettement au-dessus ou au-dessous de l'index.
    pouce_haut = lm[4].y < lm[5].y - 0.08
    pouce_bas = lm[4].y > lm[5].y + 0.08

    if _distance(lm[4], lm[8]) < 0.05 and majeur and annulaire and auriculaire:
        return "ok"
    if all(doigts) and pouce:
        return "paume"
    if all(doigts) and not pouce:
        return "quatre"
    if doigts == [True, True, False, False]:
        return "victoire"
    if index and not majeur and not annulaire and not auriculaire and pouce:
        return "pistolet"
    if not any(doigts) and pouce_haut:
        return "pouce_haut"
    if not any(doigts) and pouce_bas:
        return "pouce_bas"
    if not any(doigts) and not pouce:
        return "poing"
    if doigts == [True, False, False, False] and not pouce:
        return "pointer"
    if doigts == [True, False, False, True]:
        return "cornes"
    if doigts == [False, False, False, True] and pouce:
        return "shaka"
    if doigts == [True, True, True, False]:
        return "trois"
    return None
