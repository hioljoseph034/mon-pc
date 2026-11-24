"""Calculatrice de KITT : calculs exacts a partir de la phrase de l'utilisateur.

Securite : l'expression n'est jamais passee a eval() ni a un shell. Elle est lue comme un arbre
(ast), et seuls les nombres, les operateurs arithmetiques et quelques fonctions mathematiques
sont acceptes. Toute autre chose (noms, appels, attributs, texte) est refusee.
Limites : longueur de l'expression, puissances trop grandes, division par zero.
"""
import ast
import math
import operator
import re
import unicodedata

MAX_LONGUEUR = 200
MAX_BITS_PUISSANCE = 4000            # refuse les puissances qui produiraient un nombre gigantesque

_OPERATEURS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
               ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
               ast.Pow: operator.pow}
_UNAIRES = {ast.USub: operator.neg, ast.UAdd: operator.pos}
def _racine(x):
    if x < 0:
        raise ValueError("la racine d'un nombre négatif n'est pas un nombre réel")
    return math.sqrt(x)


_FONCTIONS = {"sqrt": _racine, "abs": abs, "min": min, "max": max, "round": round}
_CONSTANTES = {"pi": math.pi, "e": math.e}


def _minuscules(texte):
    """Minuscules et sans accents, mais le signe « - » est CONSERVE (contrairement a sec.normaliser)."""
    s = (texte or "").lower().replace("\u2019", "'")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


_DECLENCHEURS = re.compile(r"^\s*(?:kitt[ ,]+)?(?:combien\s+(?:font|fait|fais)|calcule[rz]?|calcul)\s*:?\s*")


def expression_depuis_texte(texte):
    """Transforme « 17 pour cent de 2350 » en « (17/100*2350) » ; renvoie '' si rien a calculer."""
    s = _minuscules(texte)
    s = _DECLENCHEURS.sub("", s, count=1).strip(" ?!.")
    s = re.sub(r"(\d),(\d)", r"\1.\2", s)                  # « 3,5 » -> « 3.5 » (virgule francaise)
    # Le moteur KITT remplace « cent » par « 100 » : on accepte les deux formes.
    s = re.sub(r"\s*pour\s?(?:cent|100)\s+de\s+", "% de ", s)
    s = re.sub(r"\s*pour\s?cent\s*", "%", s)
    s = re.sub(r"(\d+(?:\.\d+)?)\s*%\s*de\s*(\d+(?:\.\d+)?)", r"(\1/100*\2)", s)
    remplacements = [
        (r"\bau carre\b", "**2"), (r"\bau cube\b", "**3"),
        (r"\b(?:a la )?puissance\b", "**"),
        (r"\b(?:multiplie|multiplier|multipliee|fois)(?: par)?\b", "*"),
        (r"\b(?:divise|divisee|diviser|divisé)(?: par)?\b", "/"),
        (r"\bsur\b", "/"),
        (r"\bplus\b", "+"),
        (r"\bmoins\b", "-"),
        (r"\s*\bvirgule\b\s*", "."),
    ]
    for motif, rep in remplacements:
        s = re.sub(motif, rep, s)
    s = re.sub(r"(\d)\s*\.\s*(\d)", r"\1.\2", s)                         # « 3 . 5 » -> « 3.5 »
    s = re.sub(r"\bracine(?: carree)? de (\d+(?:\.\d+)?)", r"sqrt(\1)", s)   # « racine de 16 »
    s = re.sub(r"\s+", " ", s).strip()
    return s


def evaluer(expression):
    """Calcule l'expression ou leve ValueError avec un message en francais."""
    if not expression:
        raise ValueError("il n'y a rien à calculer")
    if len(expression) > MAX_LONGUEUR:
        raise ValueError("l'expression est trop longue")
    if re.search(r"[a-z_]", expression.replace("sqrt", "").replace("abs", "").replace("min", "")
                 .replace("max", "").replace("round", "").replace("pi", "").replace("e", "")):
        raise ValueError("je ne comprends pas ce calcul")
    try:
        arbre = ast.parse(expression, mode="eval")
    except SyntaxError:
        raise ValueError("je ne comprends pas ce calcul")
    try:
        return _evaluer_noeud(arbre.body)
    except ZeroDivisionError:
        raise ValueError("division par zéro")
    except OverflowError:
        raise ValueError("le résultat est trop grand")
    except (ArithmeticError, TypeError):
        raise ValueError("ce calcul n'a pas de résultat")


def _evaluer_noeud(n):
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
        return n.value
    if isinstance(n, ast.BinOp) and type(n.op) in _OPERATEURS:
        gauche, droite = _evaluer_noeud(n.left), _evaluer_noeud(n.right)
        if isinstance(n.op, ast.Pow):
            if abs(droite) > MAX_BITS_PUISSANCE or \
                    (abs(gauche) > 1 and abs(droite) * math.log2(abs(gauche)) > MAX_BITS_PUISSANCE):
                raise ValueError("puissance trop grande")
            resultat = _OPERATEURS[type(n.op)](gauche, droite)
            if isinstance(resultat, complex):
                raise ValueError("ce calcul n'a pas de résultat réel")
            return resultat
        return _OPERATEURS[type(n.op)](gauche, droite)
    if isinstance(n, ast.UnaryOp) and type(n.op) in _UNAIRES:
        return _UNAIRES[type(n.op)](_evaluer_noeud(n.operand))
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FONCTIONS and not n.keywords:
        args = [_evaluer_noeud(a) for a in n.args]
        if not args:
            raise ValueError("cette fonction a besoin d'au moins un nombre")
        return _FONCTIONS[n.func.id](*args)
    if isinstance(n, ast.Name) and n.id in _CONSTANTES:
        return _CONSTANTES[n.id]
    raise ValueError("cette opération n'est pas autorisée")


def formater(valeur):
    """Nombre lisible a l'oral, avec une virgule decimale."""
    if isinstance(valeur, float):
        if valeur.is_integer() and abs(valeur) < 1e15:
            valeur = int(valeur)
        else:
            valeur = round(valeur, 6)
    if isinstance(valeur, float):
        texte = f"{valeur:.6f}".rstrip("0").rstrip(".")
        return texte.replace(".", ",")
    return str(valeur)


def calculer(texte):
    """Message complet pour l'utilisateur."""
    expression = expression_depuis_texte(texte)
    if not expression:
        return "Quel calcul voulez-vous que je fasse ? Par exemple : combien font 17 pour cent de 2350."
    try:
        resultat = evaluer(expression)
    except ValueError as e:
        return f"Je ne peux pas faire ce calcul : {e}."
    return f"Le résultat est {formater(resultat)}."
