"""Physique du laboratoire de KITT : chute avec frottement de l'air, pendule a grande amplitude,
tir avec frottement. Calcul pur, sans affichage ; kitt_labo3d s'en sert pour la simulation 3D.

Methodes : integration numerique (Euler semi-implicite pour la chute, RK4 pour le pendule et le tir).
Formules exactes quand elles existent : la periode du pendule utilise les integrales elliptiques
(AGM), donc elle reste juste pour de grandes amplitudes.
"""
import math

G = 9.81
RHO_AIR = 1.2                      # kg/m3, air a 20 degres
CORPS_HUMAIN = {"masse": 70.0, "cx": 1.0, "surface": 0.7}     # chute d'une personne
BALLE_BASEBALL = {"masse": 0.145, "cx": 0.47, "surface": math.pi * 0.035 ** 2}   # tir d'une balle

MAX_ECHANTILLONS = 600


def _coefficient_frottement(objet):
    """k tel que la force de frottement vaut k * m * v^2 (par unite de masse)."""
    return 0.5 * RHO_AIR * objet["cx"] * objet["surface"] / objet["masse"]


def _echantillonner(points, maximum=MAX_ECHANTILLONS):
    if len(points) <= maximum:
        return points
    pas = len(points) / maximum
    sel = [points[int(i * pas)] for i in range(maximum)]
    sel.append(points[-1])
    return sel


def chute(hauteur, objet=CORPS_HUMAIN, dt=0.001):
    """Chute verticale depuis `hauteur` metres, avec et sans frottement."""
    t_vide = math.sqrt(2 * hauteur / G)
    k = _coefficient_frottement(objet)
    vitesse_limite = math.sqrt(G / k)
    # vd : vitesse vers le bas, positive. Integration jusqu'au sol.
    t, y, vd = 0.0, hauteur, 0.0
    trajet = [(0.0, hauteur)]
    while y > 0:
        a = G - k * vd * abs(vd)
        vd += a * dt
        y -= vd * dt
        t += dt
        trajet.append((t, max(y, 0.0)))
        if t > 10 * t_vide + 60:
            break
    points = [[0.0, y, 0.0] for _, y in _echantillonner(trajet)]
    return {"t_vide": t_vide, "t_frottement": t, "vitesse_impact": vd,
            "vitesse_vide": G * t_vide, "vitesse_limite": vitesse_limite, "points": points}


def _agm(a, b):
    for _ in range(60):
        a, b = (a + b) / 2, math.sqrt(a * b)
        if abs(a - b) < 1e-15:
            break
    return a


def periode_pendule(longueur, angle_deg):
    """Periode exacte (integrale elliptique) et periode de la formule simple, en secondes."""
    theta0 = math.radians(angle_deg)
    simple = 2 * math.pi * math.sqrt(longueur / G)
    k = min(math.sin(theta0 / 2), 1 - 1e-12)     # 180 degres : limite (periode infinie), pas d'erreur
    if k <= 0:
        return simple, simple
    K = math.pi / (2 * _agm(1.0, math.sqrt(1 - k * k)))
    return 4 * math.sqrt(longueur / G) * K, simple


def pendule(longueur, angle_deg, duree=None, dt=0.002):
    """Mouvement du pendule : points (x, y, 0) de la masse, pivot en (0, 0, 0)."""
    exacte, _ = periode_pendule(longueur, angle_deg)
    duree = duree or 2 * exacte
    theta, omega, t = math.radians(angle_deg), 0.0, 0.0
    trajet = []
    while t <= duree:
        trajet.append((t, theta))
        # RK4 sur (theta, omega)
        def f(th, om):
            return om, -(G / longueur) * math.sin(th)
        k1 = f(theta, omega)
        k2 = f(theta + dt / 2 * k1[0], omega + dt / 2 * k1[1])
        k3 = f(theta + dt / 2 * k2[0], omega + dt / 2 * k2[1])
        k4 = f(theta + dt * k3[0], omega + dt * k3[1])
        theta += dt / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])
        omega += dt / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])
        t += dt
    points = [[longueur * math.sin(th), -longueur * math.cos(th), 0.0]
              for _, th in _echantillonner(trajet)]
    return {"periode": exacte, "points": points, "duree": duree}


def tir(vitesse, angle_deg, objet=BALLE_BASEBALL, dt=0.001):
    """Tir avec frottement de l'air. Renvoie portee, hauteur max, duree et trajectoire (x, y, 0)."""
    a = math.radians(angle_deg)
    k = _coefficient_frottement(objet)
    x, y = 0.0, 0.0
    vx, vy = vitesse * math.cos(a), vitesse * math.sin(a)
    t, hmax = 0.0, 0.0
    trajet = [(x, y)]
    while True:
        v = math.hypot(vx, vy)
        ax = -k * v * vx
        ay = -G - k * v * vy
        vx += ax * dt
        vy += ay * dt
        x += vx * dt
        y += vy * dt
        t += dt
        hmax = max(hmax, y)
        trajet.append((x, y))
        if y < 0 or t > 600:
            break
    # Portee : interpolation lineaire au moment ou le projectile touche le sol
    if len(trajet) >= 2 and trajet[-1][1] < 0:
        (x1, y1), (x2, y2) = trajet[-2], trajet[-1]
        frac = y1 / (y1 - y2) if y1 != y2 else 0.0
        portee = x1 + frac * (x2 - x1)
    else:
        portee = x
    vide_portee = vitesse ** 2 * math.sin(2 * a) / G
    vide_hmax = (vitesse * math.sin(a)) ** 2 / (2 * G)
    points = [[px, py, 0.0] for px, py in _echantillonner(trajet)]
    return {"portee": portee, "hauteur_max": hmax, "duree": t, "portee_vide": vide_portee,
            "hauteur_vide": vide_hmax, "points": points}


# ---------- calculs supplementaires ----------

def ressort_amorti(masse, raideur, amortissement=0.0):
    """Oscillateur masse-ressort avec amortissement visqueux c (force = -c v).
    Renvoie la periode (s, None si pas d'oscillation), le taux d'amortissement zeta,
    et le temps pour que l'amplitude soit divisee par deux (s, None si pas d'amortissement)."""
    if masse <= 0 or raideur <= 0 or amortissement < 0:
        raise ValueError("masse et raideur doivent être positives, l'amortissement positif ou nul")
    w0 = math.sqrt(raideur / masse)
    zeta = amortissement / (2 * math.sqrt(raideur * masse))
    if zeta >= 1:
        return {"periode": None, "zeta": zeta, "demi_amplitude": None}
    periode = 2 * math.pi / (w0 * math.sqrt(1 - zeta ** 2))
    demi = None if zeta == 0 else math.log(2) / (zeta * w0)
    return {"periode": periode, "zeta": zeta, "demi_amplitude": demi}


def circuit_rc(resistance, capacite, tension=5.0):
    """Charge d'un condensateur a travers une resistance. tau = RC ; a t = tau, 63 % de la tension finale."""
    if resistance <= 0 or capacite <= 0:
        raise ValueError("résistance et capacité doivent être positives")
    tau = resistance * capacite
    return {"tau": tau, "tension_a_tau": tension * (1 - math.exp(-1)), "tension": tension}


MILIEUX_INDICE = {"air": 1.000, "eau": 1.333, "verre": 1.5, "plexiglas": 1.49, "diamant": 2.42, "glace": 1.31}


def refraction(n1, n2, angle_deg):
    """Loi de Snell-Descartes. Renvoie l'angle transmis en degrés, ou None en cas de réflexion totale."""
    sin_t = n1 * math.sin(math.radians(angle_deg)) / n2
    if abs(sin_t) > 1:
        return None
    return math.degrees(math.asin(sin_t))


# Facteurs vers l'unite de base de chaque famille ; la temperature est traitee a part.
UNITES = {
    "m/s": ("vitesse", 1.0), "km/h": ("vitesse", 1 / 3.6), "mph": ("vitesse", 0.44704), "noeud": ("vitesse", 0.514444),
    "m": ("longueur", 1.0), "km": ("longueur", 1000.0), "cm": ("longueur", 0.01), "mm": ("longueur", 0.001),
    "mile": ("longueur", 1609.344), "pied": ("longueur", 0.3048), "pouce": ("longueur", 0.0254),
    "g": ("masse", 0.001), "kg": ("masse", 1.0), "lb": ("masse", 0.45359237), "oz": ("masse", 0.0283495),
    "l": ("volume", 0.001), "ml": ("volume", 0.000001), "gallon": ("volume", 0.00378541),
    "c": ("temperature", None), "f": ("temperature", None), "k": ("temperature", None),
}


ALIAS_UNITES = {"metre": "m", "metres": "m", "kilometre": "km", "kilometres": "km", "centimetre": "cm",
                "centimetres": "cm", "millimetre": "mm", "millimetres": "mm", "pied": "pied", "pieds": "pied",
                "pouces": "pouce", "miles": "mile", "litre": "l", "litres": "l", "gramme": "g", "grammes": "g",
                "kilogramme": "kg", "kilogrammes": "kg", "livre": "lb", "livres": "lb", "celsius": "c",
                "fahrenheit": "f", "kelvin": "k", "noeuds": "noeud", "nœud": "noeud", "nœuds": "noeud",
                "gallons": "gallon", "millilitre": "ml", "millilitres": "ml"}


def convertir(valeur, de, vers):
    """Convertit une valeur entre deux unites de la meme famille. Leve ValueError sinon."""
    de, vers = de.lower(), vers.lower()
    de, vers = ALIAS_UNITES.get(de, de), ALIAS_UNITES.get(vers, vers)
    if de not in UNITES or vers not in UNITES:
        raise ValueError("unité inconnue")
    famille, facteur = UNITES[de]
    famille2, facteur2 = UNITES[vers]
    if famille != famille2:
        raise ValueError("unités de familles différentes")
    if famille == "temperature":
        celsius = {"c": valeur, "f": (valeur - 32) * 5 / 9, "k": valeur - 273.15}[de]
        return {"c": celsius, "f": celsius * 9 / 5 + 32, "k": celsius + 273.15}[vers]
    return valeur * facteur / facteur2


def energie_pendule(longueur, angle_deg, duree=None, dt=0.002, pas=200):
    """Energies cinetique et potentielle par unite de masse, dans le temps (pour un graphique).
    Renvoie (temps, ecin, epot) : listes de meme longueur."""
    exacte, _ = periode_pendule(longueur, angle_deg)
    duree = duree or 2 * exacte
    theta, omega, t = math.radians(angle_deg), 0.0, 0.0
    temps, ecin, epot = [], [], []
    intervalle = max(1, int(duree / dt / pas))
    i = 0
    while t <= duree:
        if i % intervalle == 0:
            temps.append(t)
            ecin.append(0.5 * (longueur * omega) ** 2)
            epot.append(G * longueur * (1 - math.cos(theta)))

        def f(th, om):
            return om, -(G / longueur) * math.sin(th)
        k1 = f(theta, omega)
        k2 = f(theta + dt / 2 * k1[0], omega + dt / 2 * k1[1])
        k3 = f(theta + dt / 2 * k2[0], omega + dt / 2 * k2[1])
        k4 = f(theta + dt * k3[0], omega + dt * k3[1])
        theta += dt / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])
        omega += dt / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])
        t += dt
        i += 1
    return temps, ecin, epot
