"""Simulation 3D du laboratoire : un fichier HTML autonome, ouvert dans le navigateur.

Securite et vie privee :
- Aucun telechargement : le fichier contient son propre code de dessin (pas de bibliotheque distante).
- Les donnees sont des nombres calcules par kitt_labo, injectes en JSON ; les caracteres « </ » sont
  echappes pour qu'aucune donnee ne puisse fermer la balise <script>.
- Le fichier est ecrit dans ~/.kitt/simulations, en droits prives, avec un nom unique.

Contenu : une ou plusieurs trajectoires dans une scene 3D (tir avec et sans air pour comparer),
et un graphique optionnel (energie du pendule : cinetique, potentielle, totale).
"""
import html
import json
import re
import uuid
import webbrowser
from pathlib import Path

import kitt_labo as L
import kitt_securite as sec

DOSSIER_SIMULATIONS = sec.DOSSIER / "simulations"

BORNES = {"chute": (0.5, 500.0), "pendule_longueur": (0.05, 20.0), "pendule_angle": (1.0, 175.0),
          "tir_vitesse": (1.0, 300.0), "tir_angle": (1.0, 89.0)}

GABARIT = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>KITT — __TITRE__</title>
<style>
 body{margin:0;background:#050505;color:#ff7070;font-family:Consolas,monospace}
 #bar{padding:8px 12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
 button{background:#2a0000;color:#ff9090;border:0;padding:6px 12px;cursor:pointer}
 #info{font-size:13px;white-space:pre-line}
 canvas{display:block;width:100vw;height:66vh;cursor:grab}
 #graphe{height:200px;cursor:default}
</style></head>
<body>
<div id="bar"><button id="play">Lecture / pause</button><button id="reset">Recommencer</button>
<span id="info"></span></div>
<canvas id="c"></canvas>
<canvas id="graphe"></canvas>
<script>
const D = __DONNEES__;
const c = document.getElementById('c'), ctx = c.getContext('2d');
const gc = document.getElementById('graphe'), gctx = gc.getContext('2d');
let rotY = 0.7, rotX = -0.25, zoom = 1, lecture = true, idx = 0, glisse = false, dx0 = 0, dy0 = 0;
const N = Math.max(...D.series.map(s => s.points.length));
document.getElementById('info').textContent = D.infos.join('\\n');

function taille() {
  const r = devicePixelRatio || 1;
  for (const cv of [c, gc]) {
    const cx = cv.getContext('2d');
    cv.width = cv.clientWidth * r; cv.height = cv.clientHeight * r;
    cx.setTransform(r, 0, 0, r, 0, 0);
  }
}
window.addEventListener('resize', taille); taille();

function projeter(x, y, z) {
  const px = x / D.echelle, py = (y - D.centre) / D.echelle, pz = z / D.echelle;
  const cy = Math.cos(rotY), sy = Math.sin(rotY), cx = Math.cos(rotX), sx = Math.sin(rotX);
  const x1 = px * cy + pz * sy, z1 = -px * sy + pz * cy;
  const y1 = py * cx - z1 * sx, z2 = py * sx + z1 * cx;
  const f = (c.clientHeight * 0.33 * zoom) / (4 - z2);
  return [c.clientWidth / 2 + x1 * f, c.clientHeight * 0.5 - y1 * f];
}

function ligne(a, b, couleur, epaisseur) {
  const p = projeter(...a), q = projeter(...b);
  ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]);
  ctx.strokeStyle = couleur; ctx.lineWidth = epaisseur; ctx.stroke();
}

function indiceSerie(s) {
  // Avance proportionnellement : une serie plus courte arrive a la fin en meme temps.
  const n = s.points.length;
  if (N <= 1) return n - 1;
  return Math.min(n - 1, Math.round(idx * (n - 1) / (N - 1)));
}

function dessiner() {
  ctx.clearRect(0, 0, c.clientWidth, c.clientHeight);
  for (let i = -4; i <= 4; i++) {
    const v = i * D.echelle * 0.25;
    ligne([-D.echelle, 0, v], [D.echelle, 0, v], '#331010', 1);
    ligne([v, 0, -D.echelle], [v, 0, D.echelle], '#331010', 1);
  }
  ligne([0, 0, 0], [D.echelle * 0.9, 0, 0], '#ff4040', 2);
  ligne([0, 0, 0], [0, D.echelle * 0.9, 0], '#40ff40', 2);
  ligne([0, 0, 0], [0, 0, D.echelle * 0.9], '#4080ff', 2);
  let legende = 10;
  for (const s of D.series) {
    const j = indiceSerie(s);
    for (let i = 0; i < j; i++) ligne(s.points[i], s.points[i + 1], s.couleur, 2);
    if (D.relie) ligne(D.pivot, s.points[j], '#ffd0d0', 2);
    const p = projeter(...s.points[j]);
    ctx.beginPath(); ctx.arc(p[0], p[1], 8, 0, 2 * Math.PI);
    ctx.fillStyle = s.couleur; ctx.fill();
    ctx.font = '13px Consolas'; ctx.fillStyle = s.couleur;
    ctx.fillText(s.nom, 10, legende); legende += 18;
  }
}

function dessinerGraphe() {
  if (!D.graphe) { gc.style.display = 'none'; return; }
  const W = gc.clientWidth, H = gc.clientHeight, g = D.graphe;
  gctx.clearRect(0, 0, W, H);
  const marge = 36;
  const ymax = Math.max(...g.series.flatMap(s => s.valeurs)) || 1;
  const tmax = g.temps[g.temps.length - 1] || 1;
  const X = t => marge + (W - marge - 10) * t / tmax;
  const Y = v => H - 22 - (H - 40) * v / ymax;
  gctx.strokeStyle = '#442020'; gctx.beginPath();
  gctx.moveTo(marge, 10); gctx.lineTo(marge, H - 22); gctx.lineTo(W - 10, H - 22); gctx.stroke();
  gctx.fillStyle = '#ff9090'; gctx.font = '12px Consolas';
  gctx.fillText(g.titre + ' (temps →)', marge + 4, 14);
  for (const s of g.series) {
    gctx.beginPath();
    s.valeurs.forEach((v, i) => { const x = X(g.temps[i]), y = Y(v); i ? gctx.lineTo(x, y) : gctx.moveTo(x, y); });
    gctx.strokeStyle = s.couleur; gctx.lineWidth = 2; gctx.stroke();
  }
  // curseur synchronise avec l'animation
  const k = Math.min(g.temps.length - 1, Math.round(idx * (g.temps.length - 1) / Math.max(1, N - 1)));
  gctx.strokeStyle = '#ffffff'; gctx.beginPath();
  gctx.moveTo(X(g.temps[k]), 10); gctx.lineTo(X(g.temps[k]), H - 22); gctx.stroke();
  let l = 0;
  for (const s of g.series) { gctx.fillStyle = s.couleur; gctx.fillText(s.nom, W - 170, 14 + 14 * l++); }
}

function boucle() {
  if (lecture) {
    idx += D.vitesse;
    if (idx >= N - 1) { idx = N - 1; lecture = false; }
  }
  dessiner(); dessinerGraphe();
  requestAnimationFrame(boucle);
}

c.addEventListener('mousedown', e => { glisse = true; dx0 = e.clientX; dy0 = e.clientY; });
window.addEventListener('mouseup', () => glisse = false);
window.addEventListener('mousemove', e => {
  if (!glisse) return;
  rotY += (e.clientX - dx0) * 0.01; rotX += (e.clientY - dy0) * 0.01;
  dx0 = e.clientX; dy0 = e.clientY;
});
c.addEventListener('wheel', e => { zoom = Math.min(3, Math.max(0.4, zoom * (e.deltaY > 0 ? 0.92 : 1.08))); e.preventDefault(); }, { passive: false });
document.getElementById('play').onclick = () => { if (idx >= N - 1) idx = 0; lecture = !lecture; };
document.getElementById('reset').onclick = () => { idx = 0; lecture = true; };
boucle();
</script></body></html>
"""

VIDE = {"masse": 1e9, "cx": 1.0, "surface": 1.0}      # sans frottement pratique


def _bornee(valeur, cle):
    bas, haut = BORNES[cle]
    return min(max(valeur, bas), haut)


def construire(scenario, parametres):
    """Calcule la scene. Renvoie le dictionnaire de donnees pour le gabarit."""
    if scenario == "chute":
        h = _bornee(parametres.get("hauteur", 10.0), "chute")
        r = L.chute(h)
        infos = [f"Chute de {h:g} m, corps humain de {L.CORPS_HUMAIN['masse']:g} kg",
                 f"Sans frottement : {r['t_vide']:.2f} s, vitesse {r['vitesse_vide']:.1f} m/s",
                 f"Avec l'air : {r['t_frottement']:.2f} s, vitesse à l'impact {r['vitesse_impact']:.1f} m/s",
                 f"Vitesse limite (régime permanent) : {r['vitesse_limite']:.1f} m/s"]
        return {"titre": "Chute libre", "infos": infos, "echelle": max(h, 1.0), "centre": h / 2,
                "relie": False, "pivot": [0, 0, 0], "vitesse": max(1, len(r["points"]) // 300),
                "series": [{"nom": "avec l'air", "couleur": "#ff3030", "points": r["points"]}],
                "graphe": None}
    if scenario == "pendule":
        longueur = _bornee(parametres.get("longueur", 1.0), "pendule_longueur")
        angle = _bornee(parametres.get("angle", 30.0), "pendule_angle")
        r = L.pendule(longueur, angle)
        exacte, simple = L.periode_pendule(longueur, angle)
        temps, ecin, epot = L.energie_pendule(longueur, angle)
        totale = [a + b for a, b in zip(ecin, epot)]
        infos = [f"Pendule de {longueur:g} m, écarté de {angle:g}°",
                 f"Période réelle : {exacte:.3f} s",
                 f"Formule simple (petit angle) : {simple:.3f} s, écart {100 * (exacte / simple - 1):.1f} %",
                 "Graphique : énergie par unité de masse (l'énergie totale reste constante)"]
        return {"titre": "Pendule", "infos": infos, "echelle": longueur * 1.2, "centre": -longueur / 2,
                "relie": True, "pivot": [0, 0, 0], "vitesse": max(1, len(r["points"]) // 400),
                "series": [{"nom": "masse", "couleur": "#ff3030", "points": r["points"]}],
                "graphe": {"titre": "Énergie (J/kg)", "temps": [round(t, 4) for t in temps],
                           "series": [{"nom": "cinétique", "couleur": "#40ff40", "valeurs": [round(v, 4) for v in ecin]},
                                      {"nom": "potentielle", "couleur": "#4080ff", "valeurs": [round(v, 4) for v in epot]},
                                      {"nom": "totale", "couleur": "#ffd0d0", "valeurs": [round(v, 4) for v in totale]}]}}
    if scenario == "tir":
        v = _bornee(parametres.get("vitesse", 20.0), "tir_vitesse")
        ang = _bornee(parametres.get("angle", 45.0), "tir_angle")
        r = L.tir(v, ang)
        sans = L.tir(v, ang, objet=VIDE)
        infos = [f"Balle de baseball lancée à {v:g} m/s, angle {ang:g}°",
                 f"Portée avec l'air : {r['portee']:.1f} m (sans air : {r['portee_vide']:.1f} m)",
                 f"Hauteur maximale : {r['hauteur_max']:.1f} m (sans air : {r['hauteur_vide']:.1f} m)",
                 f"Durée de vol avec l'air : {r['duree']:.2f} s"]
        echelle = max(r["portee_vide"], r["portee"], r["hauteur_vide"], 1.0) * 0.6
        return {"titre": "Tir de projectile", "infos": infos, "echelle": echelle,
                "centre": max(r["hauteur_max"], sans["hauteur_max"], 1.0) / 2,
                "relie": False, "pivot": [0, 0, 0], "vitesse": max(1, len(r["points"]) // 300),
                "series": [{"nom": "avec l'air", "couleur": "#ff3030", "points": r["points"]},
                           {"nom": "sans air", "couleur": "#40ff40", "points": sans["points"]}],
                "graphe": None}
    raise ValueError("scénario inconnu")


def _json_sur(donnees):
    """JSON sur, insérable dans une balise <script>."""
    return json.dumps(donnees, ensure_ascii=False).replace("</", "<\\/")


def generer(scenario, parametres, ouvrir=True):
    """Ecrit le fichier HTML (nom unique) et l'ouvre dans le navigateur. Renvoie le chemin."""
    donnees = construire(scenario, parametres)
    DOSSIER_SIMULATIONS.mkdir(parents=True, exist_ok=True)
    chemin = DOSSIER_SIMULATIONS / f"{scenario}_{uuid.uuid4().hex[:8]}.html"
    page = (GABARIT.replace("__TITRE__", html.escape(donnees["titre"]))
            .replace("__DONNEES__", _json_sur(donnees)))
    sec.ecrire_prive(chemin, page)
    if ouvrir:
        webbrowser.open(chemin.resolve().as_uri())
    return chemin


def extraire_parametres(texte):
    """Nombres de la phrase, dans l'ordre (virgule decimale acceptee). Le « 3 » de « 3d » est ignore."""
    sans_3d = re.sub(r"\b3\s?d\b", " ", texte or "", flags=re.IGNORECASE)
    return [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", sans_3d)]


def parametres_depuis_texte(scenario, texte):
    nombres = extraire_parametres(texte)
    if scenario == "chute":
        return {"hauteur": nombres[0] if nombres else 10.0}
    if scenario == "pendule":
        return {"longueur": nombres[0] if nombres else 1.0, "angle": nombres[1] if len(nombres) > 1 else 30.0}
    if scenario == "tir":
        return {"vitesse": nombres[0] if nombres else 20.0, "angle": nombres[1] if len(nombres) > 1 else 45.0}
    return {}
