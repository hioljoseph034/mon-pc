# KITT — assistant personnel local

KITT est un assistant qui fonctionne en grande partie hors ligne sur votre ordinateur. Il comprend la voix ou le clavier, gère votre agenda, vos tâches, vos contacts et votre mémoire, ouvre vos applications, rédige des textes, calcule, simule des expériences, et signale les situations utiles de lui-même. Internet n'est utilisé que pour les services que vous autorisez explicitement.

Pour l'installation pas à pas, voir `README_INSTALLATION.md`. Pour le modèle léger, `README_TINYLLAMA.md`. Pour la simulation 3D, `README_LABO3D.md`.

## Ce que KITT sait faire

**Hors ligne**
- **Agenda** : rendez-vous avec rappel 10 minutes avant. « ajoute un rendez-vous demain à 14 heures dentiste », « mon agenda ».
- **Tâches et notes** : « ajoute une tâche acheter du pain », « mes tâches », « note que la réunion est reportée ».
- **Minuteurs** : « minuteur de 10 minutes », « mes minuteurs ».
- **Contacts** : « ajoute le contact Paul », « ajoute le numéro de Marc 06 77 12 34 56 ».
- **Mémoire** : « retiens que… », « que sais-tu sur moi », « oublie que… », « apprends que X veut dire Y ».
- **Conversations** : plusieurs discussions séparées, à reprendre ou supprimer.
- **Fichiers** : lecture à voix haute, résumé, questions sur le contenu (texte, PDF, Word, ZIP). Joignez le fichier depuis la fenêtre.
- **Rédaction** : articles, publicités, brouillons d'e-mails (KITT prépare le brouillon, c'est vous qui l'envoyez).
- **Applications** : « ouvre la calculatrice », « lance Inkscape », après confirmation. Les outils d'administration sont refusés.
- **Ordinateur** : état du système, journal des dernières actions, sauvegarde de vos données.
- **Heure, date, aide** : « quelle heure est-il », « que sais-tu », « aide agenda ».
- **Laboratoire en texte** : chute, pendule, tir, pH, avec les formules simples.
- **Physique** (skill « physique ») : ressort amorti, circuit RC, réfraction de la lumière, conversions d'unités. Exemples : « laboratoire ressort masse 2 raideur 50 amortissement 1 », « laboratoire réfraction 30 degrés air eau », « convertis 100 km/h en m/s ».
- **Habitudes** : KITT apprend la durée de vos sessions et votre heure de coucher. « mes habitudes » montre ce qu'il a appris.

**Skills installables** (à activer avec « installe skill NOM »)
- `calcul` : calculatrice exacte, sans passer par le modèle. « combien font 17 pour cent de 2350 ».
- `labo3d` : simulations 3D dans le navigateur, avec comparaison des trajectoires (tir) et graphique d'énergie (pendule). « labo 3d pendule 1,5 mètres 60 degrés ».
- `physique` : ressort, circuit RC, réfraction, conversions (voir ci-dessus).
- `idees` et `avis` : propositions variées, et avis motivé. « donne-moi des idées pour un cadeau », « que penses-tu de Linux pour un vieil ordinateur ».
- `meteo`, `blague`, `echecs`, `jeux`, `youtube`, `appel`, `whatsapp` : voir ci-dessous.

**Avec Internet (seulement si vous l'autorisez)**
- **Météo** : `api.open-meteo.com`.
- **YouTube** : ouvre une recherche dans votre navigateur (`www.youtube.com`).
- **WhatsApp** : envoie un message après confirmation, limité à 10 par heure (`web.whatsapp.com`).

Tout est coupé par défaut. Pour autoriser un service : « active internet météo » (KITT demande confirmation), ou la fenêtre, bouton **Internet**.

**Initiatives** : KITT peut prendre la parole de lui-même : pause après une longue session, batterie faible, heure tardive, disque presque plein, tâches en attente. Il peut aussi proposer une idée, au plus une fois par jour. Il ne fait jamais seul une action : il n'envoie rien, n'appelle personne, ne ferme aucun programme et n'active pas Internet.

## Lancer

    python kitt_complet.py              fenêtre (ou navigateur si la fenêtre n'est pas disponible)
    python kitt_complet.py --web        interface dans le navigateur, sur localhost
    python kitt_complet.py --console    sans fenêtre

### Entrées au démarrage : voix et gestes

Au démarrage, KITT indique quelles entrées sont actives. Dans un terminal, il pose aussi la question : « Voix [O/n] » et « Gestes par webcam [o/N] » ; la touche Entrée garde le réglage de `config.json`, pour cette session seulement.

Options de ligne de commande, qui l'emportent sur la configuration :
- `--voix` / `--sans-voix` : activer ou couper la voix (le clavier reste toujours disponible) ;
- `--gestes` / `--sans-gestes` : activer ou couper les gestes par webcam.

Pendant la session, dites ou tapez :
- « active les gestes », « désactive les gestes » ;
- « active la voix », « désactive la voix ».

Ces réglages sont retenus dans `config.json` (clé `"entrees"`). La **webcam n'est ouverte que lorsque les gestes sont actifs**, et elle est libérée dès qu'ils sont coupés. Pour les gestes : `pip install opencv-python mediapipe`. Les gestes actifs sont : paume = réveil, victoire = agenda, poing = état du système.

**Gestes disponibles** (une main, tenue environ une demi-seconde) :

| Geste | Ce que KITT fait |
|---|---|
| Paume ouverte | Réveille KITT |
| Victoire (index et majeur) | Ouvre l'agenda |
| Poing fermé | Donne l'état du système |
| Un doigt levé (index) | Donne vos tâches |
| Pistolet (pouce et index) | Donne l'aide |
| Pouce levé | Donne l'heure |
| Pouce baissé | Donne vos habitudes |
| Signe OK (pouce et index se touchent) | Donne la date |
| Cornes (index et auriculaire) | Donne vos minuteurs |
| Shaka (pouce et auriculaire) | Donne vos notes |
| Trois doigts (index, majeur, annulaire) | Donne vos conversations |
| Quatre doigts levés (sans le pouce) | **Propose** une simulation de pendule ; elle ne s'ouvre qu'après votre « oui » |

Un geste ne fait que consulter ou proposer. Aucun geste n'envoie de message, n'appelle, ne supprime, n'ouvre de programme, n'active Internet et ne confirme une action : la simulation proposée ne s'ouvre qu'après votre confirmation vocale ou écrite. Une même commande n'est pas répétée avant quatre secondes.
Les gestes sont reconnus par MediaPipe ; la reconnaissance peut se tromper selon l'éclairage et la position de la main, et n'a pas été vérifiée sur une webcam réelle.

### Interface dans le navigateur
- KITT démarre un serveur sur **127.0.0.1** (localhost) uniquement, sur le premier port libre entre 8765 et 8774, et ouvre la page dans votre navigateur.
- L'adresse affichée dans la console contient un **jeton aléatoire** : elle n'est valable que pendant cette session. Ne la partagez pas.
- Sans ce jeton, aucune page ni commande n'est acceptée. Un autre site ouvert dans votre navigateur ne peut pas commander KITT, et le serveur n'est jamais accessible depuis le réseau.
- Au démarrage, la console affiche un bandeau : adresse complète, hôte d'écoute (127.0.0.1), port utilisé, ports déjà occupés et ignorés, heure de démarrage, et comment arrêter KITT (« au revoir », « quitte » en phrase entière, ou Ctrl+C).
- Si le port 8765 est occupé, KITT prend le suivant et l'indique dans le bandeau.
- Le même état est visible dans la page (données du serveur, avec le jeton).
- Le texte est affiché sans interprétation HTML. Vous pouvez parler ou taper, joindre un fichier par son chemin, et suivre le journal.

## Laboratoire : calculs de physique (skill « physique », à installer)

- **Ressort amorti** : « laboratoire ressort masse 2 raideur 50 amortissement 1 » donne la période et le temps pour que l'amplitude soit divisée par deux. Sans amortissement, l'oscillation continue ; trop amorti, il n'y a pas d'oscillation.
- **Circuit RC** : « laboratoire circuit 1000 0,001 5 » (résistance en ohms, capacité en farads, tension) donne la constante de temps τ = RC et la tension à t = τ (63 % de la tension finale).
- **Réfraction** (loi de Snell) : « laboratoire réfraction 30 degrés air eau » donne l'angle transmis, ou signale la réflexion totale. Milieux reconnus : air, eau, verre, plexiglas, diamant, glace.
- **Conversions** : « convertis 100 km/h en m/s », « convertis 5 pieds en mètres », « convertis 100 C en F ». Vitesses, longueurs, masses, volumes et températures. Les formes françaises (mètres, pieds, litres, celsius, livres...) sont acceptées ; la réponse affiche la forme courte.

**Valeurs manquantes** : si vous donnez quelques nombres, les autres prennent une valeur par défaut, dans l'ordre (par exemple « laboratoire ressort 2 » utilise une raideur de 10 N/m). Si vous ne donnez aucun nombre, KITT demande les valeurs, avec un exemple.

Les formules ont été vérifiées contre des valeurs connues (par exemple, la réfraction de l'air vers l'eau à 30° donne 22,03°).

## Commandes de gestion

- **Skills** : « installe skill calcul », « désinstalle skill calcul », « mes skills ».
- **Recettes** (vos propres réponses) : « crée skill nom | déclencheur1, déclencheur2 | réponse ». Une recette ne contient que du texte.
- **Initiatives** : « désactive les initiatives », « active les initiatives ».
- **Idées spontanées** : « désactive les idées », « active les idées ».
- **Aide** : « que sais-tu », puis « aide » suivi d'un thème.

## Ton de KITT

La clé `"ton"` de `config.json` règle la formulation des messages :
- `"chaleureux"` (par défaut) : confirmations et propositions plus humaines, qui suggèrent la marche à suivre ;
- `"sobre"` : formulations courtes et neutres ;
- `"espiegle"` : tournures plus légères sur les confirmations et les erreurs.

Dans la conversation libre, KITT répond avec une température de 0,7, pour plus de variété. Les réponses factuelles (calculs, lectures de documents, pH) restent à 0,3, pour rester stables.

## Configuration : `~/.kitt/config.json`

    {
      "prenom": "Michael",
      "ville": {"nom": "Batouri", "latitude": 4.4333, "longitude": 14.3667},
      "reseau": {"meteo": false, "youtube": false, "whatsapp": false},
      "jeux": {"minecraft": "C:\\Games\\Minecraft.exe"},
      "applications_perso": {"Bloc-notes": "C:\\Windows\\notepad.exe"},
      "modele_llm": "tinyllama-kitt",
      "ton": "chaleureux",
      "idees_spontanees": true,
      "entrees": {"voix": true, "gestes": false},
      "initiatives": {"activees": true, "pause_minutes": 90, "pause_auto": true}
    }

- Vérifiez les coordonnées de votre ville.
- Sous Windows, doublez les antislashs dans les chemins (`\\`).
- `modele_llm` désigne le modèle Ollama utilisé (`mistral` ou `tinyllama-kitt`). Une valeur invalide est ignorée.
- `pause_auto` à `false` garde la pause fixe, au lieu de la durée apprise.
- **Erreurs de configuration** : au démarrage, KITT signale dans la console et dans le journal chaque problème de `config.json` : clé inconnue (faute de frappe, comme « tom » au lieu de « ton »), valeur invalide, ou fichier illisible. La valeur par défaut est alors utilisée, et le problème n'est signalé qu'une fois.

## Contacts

Les contacts sont dans la base de KITT (table `contacts`). Pour WhatsApp et les appels, il faut un numéro : « ajoute le numéro de Marc 06 77 12 34 56 ». Les numéros sont normalisés en +237 par défaut. La colonne `telephone` est ajoutée automatiquement à la table existante, sans perte de données.

## Applications

- « ouvre la calculatrice » : KITT cherche dans le menu Démarrer (Windows) ou les lanceurs (Linux), et demande « oui » avant de lancer.
- Une application absente du menu peut être ajoutée à la main : « ajoute l'application Bloc-notes C:\Windows\notepad.exe ». Le chemin doit exister et est enregistré dans `config.json`.
- Refusés : PowerShell, l'invite de commandes, l'éditeur du registre, le planificateur de tâches, les programmes d'installation et de désinstallation, les terminaux.
- Seule une phrase qui commence par « ouvre », « lance » ou « démarre » est une commande.

## Sécurité

- **Pas d'exécution de code** : aucun skill, recette ni fichier téléchargé n'est exécuté. La calculatrice n'utilise pas `eval`.
- **Internet coupé par défaut**, avec une liste blanche de domaines en https, sans redirection.
- **Confirmation** pour toute action externe : appel, message WhatsApp, ouverture ou fermeture de programme, activation d'Internet, suppression.
- **Confirmation oui/non** : toute négation l'emporte (« pas d'accord » = non).
- **Limites** : au plus 10 messages WhatsApp par heure, sauvegardés pour survivre au redémarrage.
- **Fichiers** : écriture atomique (une coupure ne corrompt pas un fichier), droits 600 sous Linux et macOS.
- **Mémoire** : KITT refuse de retenir les mots de passe et les numéros de carte.
- **Nettoyage** : limité au dossier de KITT, jamais au reste du système.

## Dépendances optionnelles

- WhatsApp : `pip install pywhatkit` (Chrome installé, WhatsApp Web connecté).
- Appels : `adb` installé, téléphone Android branché et autorisé au débogage USB.
- Lecture de PDF : `pip install pypdf`. Lecture de Word : `pip install python-docx`.
- Contrôle par gestes : `pip install opencv-python mediapipe`.
- Modèle de langage : Ollama, avec `mistral` ou `tinyllama-kitt`.

## Vérifier l'installation

    python -m unittest test_kitt -v

Les **206 tests** doivent réussir (2 sont ignorés si OpenCV et MediaPipe ne sont pas installés).

## Fichiers du projet

- `kitt_complet.py` : le cœur de KITT (commandes, voix, mémoire, conversations, modes de lancement).
- `kitt_web.py` : interface dans le navigateur, sur localhost, avec jeton.
- `kitt_gestes.py` : reconnaissance des gestes de la main et leurs commandes.
- `kitt_gui.py` : la fenêtre graphique (scanner rouge, journal, Skills, Internet, Fichier).
- `kitt_skills.py` : installeur de skills, skills intégrés, recettes.
- `kitt_securite.py` : configuration, réseau sous contrôle, validation des entrées.
- `kitt_applications.py` : ouverture et ajout d'applications, avec garde-fous.
- `kitt_calcul.py` : calculatrice sans `eval`.
- `kitt_labo.py` et `kitt_labo3d.py` : physique du laboratoire (chute, pendule, tir, ressort, circuit RC, réfraction, conversions) et simulation 3D en HTML.
- `kitt_idees.py` : idées et avis, avec la détection des sujets sensibles.
- `kitt_initiatives.py` : initiatives et apprentissage des habitudes.
- `kitt_ton.py` : formulations variées et ton des messages.
- `kitt_fiabilite.py` : nettoyage des réponses du modèle, détection du français, passages pertinents.
- `kitt_aide.py` : aide intégrée, avec des exemples vérifiés par les tests.
- `evaluer_modele.py` : mesure la fiabilité du modèle local.
- `test_kitt.py` : les tests.

## Limites connues

- **Non vérifié sur une vraie machine** : la fenêtre graphique, la page du navigateur (le code JavaScript est valide, mais l'affichage n'a pas été vu), la voix (micro et synthèse), le lancement d'applications sous Windows, WhatsApp, la météo, YouTube et les appels adb. Leur logique est testée, pas leur échange réel avec le système ou les services.
- **Modèle léger** : TinyLlama parle un français approximatif et invente parfois. Ses idées, avis et réponses libres sont à prendre avec prudence. Mistral est nettement meilleur si votre machine le permet.
- **Données en clair** : la base, les conversations et les sauvegardes ne sont pas chiffrées. Protégez le support qui les contient.
- **Valeurs hors limites** dans les simulations 3D : corrigées sans avertissement.
- **Profil d'habitudes** : un seul par machine. Plusieurs personnes sur le même ordinateur mélangeraient leurs habitudes.
- **Recettes modifiées** : un changement de déclencheur prend effet immédiatement.
