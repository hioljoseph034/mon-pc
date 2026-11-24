# KITT — Installer le modèle léger tinyllama-kitt

Ce guide explique comment faire tourner KITT avec **TinyLlama**, un modèle de langage léger,
à partir du fichier GGUF téléchargé depuis Hugging Face. Il convient aux machines modestes.
Pour un usage sérieux, préférez Mistral (voir `README_INSTALLATION.md`, étape 6).

> Limite : TinyLlama (1,1 milliard de paramètres) parle un français approximatif et peut inventer.
> Il convient à la conversation simple. Il est peu fiable pour résumer un document ou rédiger un e-mail.

---

## Prérequis

- **Ollama** installé : https://ollama.com (installateur à double-cliquer, comme un logiciel classique).
- Environ **1 Go** d'espace disque libre et quelques centaines de Mo de mémoire vive.
- KITT déjà décompressé (dossier `kitt`).

## Étape 1 : télécharger le modèle

Ouvrez la page suivante et téléchargez le fichier `tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf` :

https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/blob/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf

Sur la page, cliquez sur l'icône de téléchargement (flèche vers le bas), à droite du nom du fichier.

Placez ce fichier dans un dossier dédié, par exemple `C:\KITT\modeles` (Windows) ou `~/kitt-modeles` (Linux).

## Étape 2 : créer le fichier de configuration du modèle

Dans le même dossier, créez un fichier texte nommé **`Modelfile`**, sans extension, avec exactement cette ligne :

```
FROM ./tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
```

Sous Windows, le Bloc-notes peut ajouter une extension `.txt` au nom. Pour l'éviter, choisissez
« Tous les fichiers » dans la liste « Type » au moment de l'enregistrement, et nommez le fichier `Modelfile`.

## Étape 3 : enregistrer le modèle dans Ollama

Ouvrez un terminal dans le dossier `modeles` et lancez :

```
ollama create tinyllama-kitt -f Modelfile
```

La commande affiche des lignes de progression, puis « success ». Si vous voyez une erreur
« no such file », vérifiez que le nom du fichier GGUF correspond exactement à la ligne `FROM`.

## Étape 4 : tester le modèle

```
ollama run tinyllama-kitt "Bonjour, qui es-tu ?"
```

Une réponse s'affiche. Pour quitter le mode interactif, tapez `/bye` (si la commande est lancée sans texte).

Vérifiez aussi que la liste contient le modèle :

```
ollama list
```

## Étape 5 : indiquer le modèle à KITT

Ouvrez le fichier `config.json` de KITT :
- Windows : `C:\Users\VotreNom\.kitt\config.json`
- Linux : `~/.kitt/config.json`

Ajoutez la ligne suivante au niveau principal du fichier (pensez à la virgule qui sépare les lignes) :

```json
"modele_llm": "tinyllama-kitt"
```

Exemple complet :

```json
{
  "prenom": "Michael",
  "modele_llm": "tinyllama-kitt",
  "ville": {"nom": "Batouri", "latitude": 4.4333, "longitude": 14.3667},
  "reseau": {"meteo": false, "youtube": false, "whatsapp": false}
}
```

Si le fichier n'existe pas encore, créez-le avec ce contenu. Pour revenir à Mistral, remettez `"mistral"`.

## Étape 6 : lancer KITT

Dans le dossier `kitt` :

```
python kitt_complet.py
```

Tapez une phrase libre. Si KITT répond « Le modèle de langage local ne répond pas », vérifiez
qu'Ollama tourne (icône dans la barre des tâches sous Windows) et que `ollama run tinyllama-kitt` fonctionne.

---

## Dépannage

| Problème | Solution |
|---|---|
| `ollama create` : « no such file » | Le nom du fichier dans `Modelfile` ne correspond pas. Vérifiez les majuscules et le suffixe `.gguf`. |
| Le modèle répond en anglais | Normal pour TinyLlama. Demandez explicitement « Réponds en français. » |
| Réponses incohérentes ou inventées | Limite du modèle. Revenez à Mistral pour un usage sérieux. |
| Réponse très lente | Fermez les autres applications lourdes. TinyLlama est léger, mais votre machine peut être très chargée. |
| KITT utilise toujours mistral | Vérifiez `config.json` : la valeur doit être exactement `"tinyllama-kitt"`, entre guillemets. |
| Une valeur de `config.json` est ignorée | KITT ignore les valeurs invalides (espaces, caractères spéciaux) et garde `mistral`. |

## Vérifier l'installation

```
python -m unittest test_kitt -v
```

Les 206 tests doivent réussir.

## Ce qui n'est pas encore vérifié

- Le téléchargement du fichier et le comportement exact de Ollama avec ce GGUF n'ont pas été testés ici, car l'accès au réseau est coupé dans l'environnement de test.
- La qualité des réponses en français doit être évaluée sur votre machine.

## Mesurer la fiabilité

Pour comparer TinyLlama et Mistral sur votre machine, avec Ollama lancé :

```
python evaluer_modele.py tinyllama-kitt
python evaluer_modele.py mistral
```

Le script pose des questions à réponse connue et indique celles qui échouent. Vous pouvez ajouter vos propres cas dans `kitt_fiabilite.py` (variable `CAS_REFERENCE`).
