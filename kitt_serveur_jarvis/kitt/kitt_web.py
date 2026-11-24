"""Interface de KITT dans le navigateur, servie sur 127.0.0.1 (localhost) uniquement.

Securite :
- Le serveur n'ecoute que sur 127.0.0.1 : il n'est jamais accessible depuis le reseau.
- Un jeton aleatoire, cree a chaque demarrage, est exige pour la page et pour chaque requete.
  Un site quelconque ouvert dans le navigateur ne peut donc pas commander KITT.
- L'en-tete Host doit etre localhost ou 127.0.0.1 (protection contre la reattribution DNS).
- Une requete POST doit venir de la page elle-meme (en-tete Origin verifie).
- Le texte affiche dans la page est insere avec textContent, jamais innerHTML.
- Aucun en-tete CORS n'est envoye : aucune autre page ne peut lire les reponses.
"""
import collections
import json
import secrets
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HOTE = "127.0.0.1"                       # jamais 0.0.0.0 : pas d'acces depuis le reseau
HOTES_ACCEPTES = ("localhost", "127.0.0.1")
PORTS_POSSIBLES = range(8765, 8775)
MAX_TEXTE = 500
MAX_CORPS = 4000

PAGE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>KITT</title>
<style>
 body{margin:0;background:#050505;color:#ff7070;font-family:Consolas,monospace;min-height:100vh}
 h1{text-align:center;color:#ff2a2a;letter-spacing:6px;margin:14px 0 6px}
 #scanner{display:flex;justify-content:center;gap:6px;margin:10px 0}
 .seg{width:46px;height:26px;background:#200000;border-radius:3px;transition:background .12s}
 .parle .seg{animation:pulse .5s infinite alternate}
 @keyframes pulse{from{opacity:.4}to{opacity:1}}
 #statut{text-align:center;color:#ff6a6a;min-height:20px}
 #reseau{text-align:center;color:#884444;font-size:12px;min-height:16px}
 #journal{height:46vh;overflow-y:auto;margin:10px;padding:10px;background:#0b0b0b;white-space:pre-wrap;font-size:14px}
 .ligne{margin:2px 0}
 #bas{display:flex;gap:8px;margin:0 10px 10px}
 input{background:#161616;color:#ff8080;border:0;padding:10px;font-family:inherit;font-size:14px}
 #entree{flex:1}
 button{background:#2a0000;color:#ff9090;border:0;padding:10px 14px;cursor:pointer}
 #chemin{width:40%}
</style></head>
<body>
<h1>K . I . T . T</h1>
<div id="scanner"></div>
<div id="statut"></div>
<div id="reseau"></div>
<div id="journal"></div>
<div id="bas">
  <input id="entree" placeholder="Parlez ou tapez une commande..." autocomplete="off">
  <input id="chemin" placeholder="Chemin d'un fichier à joindre" autocomplete="off">
  <button id="joindre">Joindre</button>
</div>
<script>
const JETON = new URLSearchParams(location.search).get('jeton') || '';
const LIBELLES = {veille: 'EN VEILLE - dites « KITT »', ecoute: 'JE VOUS ÉCOUTE',
                  reflexion: 'RÉFLEXION...', parle: 'KITT PARLE'};
const scanner = document.getElementById('scanner');
for (let i = 0; i < 8; i++) { const d = document.createElement('div'); d.className = 'seg'; scanner.appendChild(d); }
const journal = document.getElementById('journal');
let depuis = 0;

async function api(chemin, options = {}) {
  options.headers = Object.assign({'X-Kitt-Jeton': JETON}, options.headers || {});
  const r = await fetch(chemin, options);
  if (!r.ok) throw new Error('Accès refusé (' + r.status + ')');
  return r.json();
}

async function rafraichir() {
  try {
    const d = await api('/api/etat?depuis=' + depuis);
    document.body.className = d.etat;
    document.getElementById('statut').textContent = LIBELLES[d.etat] || '';
    document.getElementById('reseau').textContent = d.reseau;
    for (const [n, texte] of d.lignes) {
      const p = document.createElement('div');
      p.className = 'ligne';
      p.textContent = texte;
      journal.appendChild(p);
      depuis = Math.max(depuis, n);
    }
    if (d.lignes.length) journal.scrollTop = journal.scrollHeight;
    if (!d.actif) document.getElementById('statut').textContent = 'KITT est en veille. Vous pouvez fermer cette page.';
  } catch (e) {
    document.getElementById('statut').textContent = e.message;
  }
}

async function envoyer(chemin, corps) {
  return api(chemin, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(corps)});
}

document.getElementById('entree').addEventListener('keydown', e => {
  if (e.key !== 'Enter') return;
  const texte = e.target.value.trim();
  e.target.value = '';
  if (texte) envoyer('/api/commande', {texte}).catch(err => alert(err.message));
});
document.getElementById('joindre').addEventListener('click', () => {
  const chemin = document.getElementById('chemin').value.trim();
  if (chemin) envoyer('/api/fichier', {chemin}).catch(err => alert(err.message));
});
rafraichir();
setInterval(rafraichir, 300);
</script></body></html>
"""


class InterfaceWeb:
    """Meme contrat que l'interface Tk : .kitt, .log(ligne), .run()."""

    def __init__(self, port=None):
        self.kitt = None
        self.jeton = secrets.token_urlsafe(24)
        self.lignes = collections.deque(maxlen=500)
        self.numero = 0
        self.verrou = threading.Lock()
        self.port = port
        self.serveur = None
        self.url = None
        self.demarre = None               # moment ou le serveur a commence a ecouter
        self.ports_occupes = []           # ports essayes puis refuses (deja utilises)

    def log(self, ligne):
        with self.verrou:
            self.numero += 1
            self.lignes.append((self.numero, str(ligne)))

    def lignes_depuis(self, depuis):
        with self.verrou:
            return [(n, l) for n, l in self.lignes if n > depuis]

    def _demarrer_serveur(self):
        ports = [self.port] if self.port is not None else list(PORTS_POSSIBLES)
        for p in ports:
            try:
                self.serveur = ThreadingHTTPServer((HOTE, p), GestionnaireWeb)
                self.serveur.ui = self
                self.port = self.serveur.server_address[1]     # 0 : le systeme choisit un port libre
                self.demarre = datetime.now()
                return
            except OSError:
                self.ports_occupes.append(p)
                continue
        raise OSError("aucun port libre entre 8765 et 8774")

    def infos_serveur(self):
        return {"hote": HOTE, "port": self.port,
                "demarre": self.demarre.isoformat(timespec="seconds") if self.demarre else None,
                "ports_occupes": list(self.ports_occupes)}

    def bandeau(self):
        """Ce qui s'affiche dans la console au demarrage du serveur."""
        occupes = (", ".join(str(p) for p in self.ports_occupes) + " (déjà utilisés, ignorés)"
                   if self.ports_occupes else "aucun")
        lignes = [
            "=" * 64,
            "  KITT — serveur navigateur",
            "=" * 64,
            f"  Adresse        : {self.url}",
            f"  Hôte d'écoute  : {HOTE} (accessible sur ce PC uniquement)",
            f"  Port           : {self.port}",
            f"  Ports occupés  : {occupes}",
            f"  Démarré à      : {self.demarre:%H:%M:%S}" if self.demarre else "  Démarré à      : ?",
            "  Jeton          : valable pour cette session seulement, ne le partagez pas",
            "  Arrêt          : dites « au revoir » ou « quitte » (phrase entière), ou Ctrl+C",
            "=" * 64,
        ]
        return "\n".join(lignes)

    def run(self):
        """Sert la page jusqu'a la fermeture de KITT. Bloquant, comme l'interface Tk."""
        self._demarrer_serveur()
        self.url = f"http://localhost:{self.port}/?jeton={self.jeton}"
        threading.Thread(target=self.serveur.serve_forever, daemon=True).start()
        print(self.bandeau())
        try:
            webbrowser.open(self.url)
        except Exception:
            print("(Le navigateur ne s'est pas ouvert : copiez l'adresse ci-dessus.)")
        try:
            while self.kitt is None or self.kitt.actif:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nInterruption demandée (Ctrl+C).")
        finally:
            self.serveur.shutdown()
            self.serveur.server_close()
            print(f"Serveur KITT arrêté (port {self.port}).")


def _hote_accepte(valeur):
    return (valeur or "").split(":")[0].strip("[]") in HOTES_ACCEPTES


class GestionnaireWeb(BaseHTTPRequestHandler):
    server_version = "KITT"

    def log_message(self, format, *args):      # pas de journal HTTP sur la console
        pass

    def _envoyer(self, code, corps, type_="application/json; charset=utf-8"):
        donnees = corps if isinstance(corps, bytes) else json.dumps(corps, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(donnees)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(donnees)

    def _controle(self, jeton_recu, exiger_origine=False):
        """Renvoie True si la requete est acceptee. Sinon, la reponse 403 est deja envoyee."""
        ui = self.server.ui
        if not _hote_accepte(self.headers.get("Host")):
            self._envoyer(403, {"erreur": "hôte refusé"})
            return False
        if not jeton_recu or not secrets.compare_digest(jeton_recu, ui.jeton):
            self._envoyer(403, {"erreur": "jeton absent ou invalide"})
            return False
        if exiger_origine:
            origine = self.headers.get("Origin")
            attendue = {f"http://localhost:{ui.port}", f"http://127.0.0.1:{ui.port}"}
            if origine not in attendue:
                self._envoyer(403, {"erreur": "origine refusée"})
                return False
        return True

    def do_GET(self):
        url = urlparse(self.path)
        q = parse_qs(url.query)
        ui = self.server.ui
        if url.path == "/":
            if not _hote_accepte(self.headers.get("Host")):
                return self._envoyer(403, {"erreur": "hôte refusé"})
            if not secrets.compare_digest(q.get("jeton", [""])[0], ui.jeton):
                return self._envoyer(403, b"Ouvrez l'adresse affichee dans la console de KITT.",
                                     "text/plain; charset=utf-8")
            return self._envoyer(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        if url.path == "/api/etat":
            if not self._controle(self.headers.get("X-Kitt-Jeton")):
                return
            try:
                depuis = max(0, int(q.get("depuis", ["0"])[0]))
            except ValueError:
                depuis = 0
            k = ui.kitt
            etat = k.etat if k else "veille"
            actif = bool(k and k.actif)
            reseau = _resume_reseau()
            return self._envoyer(200, {"etat": etat, "actif": actif, "reseau": reseau,
                                       "lignes": ui.lignes_depuis(depuis),
                                       "serveur": ui.infos_serveur()})
        return self._envoyer(404, {"erreur": "introuvable"})

    def _corps(self):
        try:
            longueur = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if longueur <= 0 or longueur > MAX_CORPS:
            return None
        try:
            return json.loads(self.rfile.read(longueur).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def do_POST(self):
        url = urlparse(self.path)
        if not self._controle(self.headers.get("X-Kitt-Jeton"), exiger_origine=True):
            return
        ui = self.server.ui
        corps = self._corps()
        if not isinstance(corps, dict):
            return self._envoyer(400, {"erreur": "requête invalide"})
        if ui.kitt is None or not ui.kitt.actif:
            return self._envoyer(409, {"erreur": "KITT n'est pas prêt"})
        if url.path == "/api/commande":
            texte = str(corps.get("texte", "")).strip()[:MAX_TEXTE]
            if not texte:
                return self._envoyer(400, {"erreur": "texte vide"})
            ui.kitt.texte_q.put(texte)
            return self._envoyer(200, {"ok": True})
        if url.path == "/api/fichier":
            chemin = Path(str(corps.get("chemin", "")).strip().strip('"'))
            if not chemin.is_file():
                return self._envoyer(400, {"erreur": "fichier introuvable"})
            ui.kitt.fichier_courant = chemin
            ui.kitt.texte_q.put("quel est le fichier joint")
            return self._envoyer(200, {"ok": True})
        return self._envoyer(404, {"erreur": "introuvable"})


def _resume_reseau():
    try:
        import kitt_securite as sec
        actifs = [s for s in sec.SERVICES_RESEAU if sec.reseau_active(s)]
    except Exception:
        actifs = []
    return "INTERNET : " + ", ".join(actifs) if actifs else "HORS LIGNE (aucun service autorisé)"
