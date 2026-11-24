# KITT en ligne (bot Telegram)

Version serveur de KITT, réservée à un seul utilisateur. Elle reprend le cœur de la version de bureau
(mémoire, agenda, tâches, notes, minuteurs, contacts, rédaction, calculs, physique, discussion locale)
et la relie à Telegram.

## Ce qui est retiré

Tout ce qui agit sur la machine : ouverture et fermeture d'applications, fichiers locaux, état du système,
voix de sortie, gestes, simulations 3D dans le navigateur, jeux, échecs, YouTube, appels et WhatsApp.

## Ce qui est ajouté

- **Messages vocaux Telegram** : envoyez un message vocal, KITT le transcrit (Vosk, hors ligne) et exécute la demande.
  Il faut `ffmpeg` (`sudo apt install ffmpeg`) et un modèle français, par exemple `vosk-model-small-fr`.
  Décompressez-le dans `~/.kitt/` (par exemple `~/.kitt/vosk-model-small-fr-0.22`). Sans ces éléments, KITT
  répond simplement qu'il ne peut pas traiter le vocal.
- **Réponses vocales** : KITT répond aussi en message vocal, avec la voix française d'espeak-ng.
  Réglage : « désactive la voix » et « active la voix », retenu dans `~/.kitt/config.json`.
  Il faut `espeak-ng` (`sudo apt install espeak-ng`). La voix est robotique, dans l'esprit de K2000 ;
  une voix plus naturelle (Piper) peut être ajoutée plus tard.
- **Labo 3D** : « labo 3d pendule 1,5 mètres 60 degrés » envoie un fichier HTML autonome. Ouvrez-le dans le navigateur
  de votre téléphone ; il fonctionne sans connexion. Installez d'abord le module : « installe skill labo3d ».
- **Recherche pour le labo** : « labo recherche effet Doppler » interroge Wikipédia (fr, puis en) et répond
  à partir des extraits, avec les adresses des sources écrites par le code. Il faut autoriser Internet une fois :
  « active internet labo_web ». Seules les pages de Wikipédia sont interrogées.
  Test de l'accès depuis le serveur : `curl -s -o /dev/null -w "%{http_code}\n" "https://fr.wikipedia.org/w/api.php?action=query&format=json"`
  doit renvoyer `200`.
- **Sauvegarde** : « envoie la sauvegarde » renvoie un fichier zip contenant la base (agenda, tâches, contacts,
  mémoire) et les conversations.

## Prérequis

- Ollama installé, avec le modèle `qwen2.5-kitt` (voir la configuration du modèle dans le guide d'installation).
- Python 3.12 et `pip install -r requirements-serveur.txt`.
- Paquets système : `sudo apt install ffmpeg espeak-ng`.
- Un bot créé avec **BotFather** (token).
- Votre identifiant Telegram numérique (obtenu avec **@userinfobot**).

## Configuration

Copiez `.env.example` en `.env` et remplissez `TELEGRAM_TOKEN` et `TELEGRAM_OWNER_ID`. Ce fichier ne doit jamais
être publié. Sur le serveur : `chmod 600 .env`.

Le réglage `modele_llm` de `~/.kitt/config.json` vaut `qwen2.5-kitt` par défaut.

## Lancer

Sur une sandbox sans systemd :

    ./demarrer.sh

Sur un VPS avec systemd : copiez `kitt-bot.service` dans `/etc/systemd/system/`, adaptez les chemins,
puis `sudo systemctl enable --now kitt-bot`.

Dans les deux cas, vérifiez d'abord à la main avec `python3 kitt_telegram.py`.

## Sécurité

- Seul l'identifiant défini dans `TELEGRAM_OWNER_ID` reçoit des réponses. Les autres messages sont ignorés.
- Le modèle tourne sur le serveur ; aucune donnée n'est envoyée à un service externe pour la discussion.
- La base et les conversations sont dans `~/.kitt/`. Sauvegardez ce dossier régulièrement.
- Les actions externes (activation d'Internet) restent soumises à votre confirmation.
- **Attention à la sauvegarde** : le fichier envoyé transite par les serveurs de Telegram et y reste jusqu'à
  suppression dans la conversation. Ne l'envoyez pas si vous ne voulez pas que vos données y soient stockées,
  et supprimez les anciennes sauvegardes du chat.
- Les messages vocaux sont transcrits sur le serveur, mais ils transitent par Telegram comme tout message.

## Limites connues

- Les rappels et minuteurs ne sont vérifiés que lorsque le bot tourne.
- La sandbox peut s'arrêter : vérifiez qu'elle reste démarrée en permanence sur votre compte.
- Les réponses du modèle prennent quelques secondes sur 4 vCPU.
