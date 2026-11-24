# KITT — Guide d'installation

Ce guide explique comment installer et lancer KITT sur Windows ou Linux.
Le projet a été vérifié sous Linux avec Python 3.12. Sous Windows, les étapes sont les mêmes,
mais elles n'ont pas encore été testées sur une vraie machine.

---

## 1. Préparer Python

- Installez **Python 3.12** ou plus récent depuis https://www.python.org.
- Sous Windows, cochez **« Add python.exe to PATH »** pendant l'installation.
  L'interface graphique utilise tkinter, fourni avec Python sur Windows.
- Vérifiez dans un terminal :

```
python --version
```

## 2. Décompresser le projet

Décompressez `kitt.zip` dans un dossier, par exemple `C:\KITT`.
Vous devez obtenir un dossier `kitt` contenant le cœur (`kitt_complet.py`), les modules
(`kitt_skills.py`, `kitt_securite.py`, `kitt_gui.py`, `kitt_applications.py`, `kitt_calcul.py`,
`kitt_labo.py`, `kitt_labo3d.py`, `kitt_idees.py`, `kitt_initiatives.py`, `kitt_ton.py`,
`kitt_fiabilite.py`, `kitt_aide.py`), `evaluer_modele.py`, les tests (`test_kitt.py`) et les guides `README*.md`.

## 3. Installer les dépendances

Ouvrez un terminal dans le dossier `kitt` et lancez :

```
pip install vosk sounddevice pyttsx3 psutil
```

Dépendances optionnelles, selon ce que vous voulez utiliser :

| Fonction | Commande |
|---|---|
| WhatsApp | `pip install pywhatkit` (Google Chrome installé, WhatsApp Web connecté) |
| Lecture de PDF | `pip install pypdf` |
| Lecture de Word (.docx) | `pip install python-docx` |
| Contrôle par gestes (webcam) | `pip install opencv-python mediapipe` |

## 4. Installer le modèle vocal français

1. Téléchargez **vosk-model-small-fr-0.22** sur https://alphacephei.com/vosk/models.
2. Décompressez-le dans votre dossier personnel, dans `.kitt` :
   - Windows : `C:\Users\VotreNom\.kitt\vosk-model-small-fr-0.22`
   - Linux : `~/.kitt/vosk-model-small-fr-0.22`

KITT le trouve automatiquement. Sans ce modèle, il fonctionne uniquement au clavier.

## 5. Installer une voix française (Windows)

Allez dans **Paramètres > Heure et langue > Voix > Ajouter des voix** et installez une voix en français.
Sans cela, KITT parle avec une voix anglaise.

## 6. Installer le modèle de langage local (optionnel)

Ce modèle sert à la discussion libre, à la rédaction et à la lecture de documents.

1. Installez **Ollama** depuis https://ollama.com.
2. Dans un terminal :

```
ollama pull mistral
```

Sans Ollama, toutes les commandes restent disponibles, mais KITT ne peut pas rédiger ni discuter librement.

Pour une machine modeste, utilisez le modèle léger décrit dans `README_TINYLLAMA.md`.
Le nom du modèle se règle dans `config.json` avec la clé `"modele_llm"`.

## 7. Lancer KITT

Dans le dossier `kitt` :

```
python kitt_complet.py
```

La fenêtre s'ouvre. Pour lancer sans fenêtre :

```
python kitt_complet.py --console
```

Pour lancer dans le navigateur, sur localhost :

```
python kitt_complet.py --web
```

Au démarrage, le serveur affiche son adresse, son port et les ports déjà occupés. Les entrées se règlent
avec `--voix`, `--sans-voix`, `--gestes` et `--sans-gestes`, ou dans le terminal au moment de la question
« Voix » et « Gestes par webcam ». Pendant la session : « active les gestes », « désactive la voix », etc.

**Premier essai conseillé** : tapez « mes habitudes » ou « ajoute le numéro de Marc 06 77 12 34 56 »
pour vérifier que la base de données fonctionne.

## 8. Configuration

Le fichier de configuration est `config.json` dans votre dossier `.kitt` :
- Windows : `C:\Users\VotreNom\.kitt\config.json`
- Linux : `~/.kitt/config.json`

Il est créé à la première modification. Exemple :

```json
{
  "prenom": "Michael",
  "ville": {"nom": "Batouri", "latitude": 4.4333, "longitude": 14.3667},
  "reseau": {"meteo": false, "youtube": false, "whatsapp": false},
  "jeux": {"minecraft": "C:\\Games\\Minecraft.exe"},
  "applications_perso": {},
  "modele_llm": "tinyllama-kitt",
  "ton": "chaleureux",
  "idees_spontanees": true,
  "entrees": {"voix": true, "gestes": false},
  "initiatives": {"activees": true, "pause_minutes": 90, "pause_auto": true}
}
```

- Vérifiez les coordonnées de votre ville.
- Dans `jeux`, indiquez le chemin exact du programme. Sous Windows, doublez les antislashs (`\\`).
- Internet reste coupé tant que vous ne l'autorisez pas, à la voix (« active internet météo ») ou depuis la fenêtre.
- `modele_llm` : `"mistral"` si vous avez installé Mistral, `"tinyllama-kitt"` si vous suivez `README_TINYLLAMA.md`.
  Une valeur invalide est ignorée, et KITT utilise alors la valeur par défaut.
- `ton` : `"chaleureux"`, `"sobre"` ou `"espiegle"`. Voir le README principal.
- `idees_spontanees` : `false` pour que KITT ne propose plus d'idée de lui-même.
- `entrees` : `voix` (micro) et `gestes` (webcam, désactivés par défaut). Le réglage du démarrage ne vaut que pour la session ; la commande vocale le retient.

## 9. Vérifier l'installation

```
python -m unittest test_kitt -v
```

Les **206 tests** doivent réussir (2 sont ignorés si OpenCV et MediaPipe ne sont pas installés). En cas d'échec, copiez le message d'erreur complet.

---

## Linux

- Dépendances système : `sudo apt install libportaudio2 espeak-ng python3-tk`
- Puis les mêmes commandes `pip` qu'au point 3.
- Dossier des données : `~/.kitt/`.

---

## Dépannage

| Message affiché par KITT | Cause probable | Solution |
|---|---|---|
| « vosk ou sounddevice absent » | Bibliothèques manquantes | Relancez `pip install vosk sounddevice` |
| « modèle vocal introuvable » | Modèle mal placé | Vérifiez le dossier du point 4 |
| « micro indisponible » | Micro non détecté ou occupé | Vérifiez les réglages audio, puis saisissez au clavier |
| « Le modèle de langage local ne répond pas » | Ollama non lancé | Démarrez Ollama, puis `ollama pull mistral` |
| « psutil » manquant | Bibliothèque absente | `pip install psutil` |

## Ce qui n'est pas encore vérifié

- L'installation sous Windows n'a pas été testée.
- Le micro, la reconnaissance vocale et la synthèse n'ont pas encore été lancés sur une vraie machine.
- WhatsApp, la météo, YouTube et les appels Android n'ont pas été testés contre les vrais services.

Si une étape bloque, notez l'étape et le message exact, puis envoyez-les pour diagnostic.
