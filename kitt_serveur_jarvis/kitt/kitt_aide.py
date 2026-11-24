"""Aide de KITT : ce qu'il sait faire, et la commande exacte pour chaque fonction.

Les exemples sont verifies par les tests : chaque phrase doit reellement declencher une fonction.
Dites « aide » suivi d'un theme (« aide agenda », « aide labo 3d ») pour le detail, ou « que sais-tu »
pour le sommaire.
"""
import kitt_securite as sec

# theme -> (titre, resume, [(commande exemple, ce qui se passe)])
THEMES = {
    "agenda": ("Agenda", "Rendez-vous avec rappel 10 minutes avant l'heure.", [
        ("ajoute un rendez-vous demain à 14 heures dentiste", "crée le rendez-vous et le rappelle"),
        ("mon agenda", "lit vos prochains rendez-vous"),
        ("supprime le rendez-vous dentiste", "supprime le rendez-vous correspondant")]),
    "taches": ("Tâches et notes", "Une liste de tâches et des notes écrites.", [
        ("ajoute une tâche acheter du pain", "ajoute la tâche à la liste"),
        ("mes tâches", "lit les tâches en cours"),
        ("tâche terminée acheter du pain", "marque la tâche comme faite"),
        ("note que la réunion est reportée", "enregistre la note"),
        ("mes notes", "lit vos notes")]),
    "rappels": ("Minuteurs", "Des minuteurs qui vous préviennent à l'heure dite.", [
        ("minuteur de 10 minutes", "lance un minuteur de dix minutes"),
        ("mes minuteurs", "liste les minuteurs en cours"),
        ("annule le minuteur", "annule le minuteur en cours")]),
    "contacts": ("Contacts", "Vos contacts, avec leur adresse e-mail et leur numéro.", [
        ("ajoute le contact Paul", "crée le contact Paul"),
        ("mes contacts", "liste vos contacts"),
        ("supprime le contact Paul", "supprime le contact"),
        ("ajoute le numéro de Marc 06 77 12 34 56", "enregistre le numéro de Marc (utile pour appels et WhatsApp)")]),
    "memoire": ("Mémoire", "KITT retient ce que vous lui demandez de retenir.", [
        ("retiens que ma voiture est une Trans Am", "garde l'information"),
        ("que sais-tu sur moi", "lit ce qu'il retient"),
        ("oublie que ma voiture est une Trans Am", "efface l'information"),
        ("apprends que blague veut dire histoire drôle", "apprend un alias")]),
    "conversations": ("Conversations", "Plusieurs discussions séparées, à reprendre quand vous voulez.", [
        ("nouvelle conversation", "ouvre une nouvelle discussion"),
        ("mes conversations", "liste vos discussions"),
        ("reprends la conversation", "rouvre une discussion"),
        ("supprime la conversation", "supprime la discussion")]),
    "fichiers": ("Fichiers", "Lecture, résumé et questions sur un fichier. Joignez le fichier depuis la fenêtre (bouton Fichier).", [
        ("lis le document", "lit le texte à voix haute"),
        ("résume le fichier", "rédige un résumé dans ~/.kitt/resumes"),
        ("question sur le fichier quand est le rendez-vous", "répond d'après le document"),
        ("quel est le fichier joint", "indique le fichier en cours"),
        ("reprends la lecture", "reprend une lecture interrompue")]),
    "redaction": ("Rédaction", "Articles, documents, publicités et brouillons d'e-mails, que KITT peut lire à voix haute.", [
        ("rédige un article sur l'eau potable", "écrit un article et le sauvegarde"),
        ("fais une publicité pour mon restaurant", "rédige une publicité"),
        ("écris un e-mail à Paul pour la réunion", "prépare un brouillon dans votre messagerie : vous l'envoyez")]),
    "applications": ("Applications", "Ouvre les programmes de votre ordinateur, après confirmation.", [
        ("ouvre la calculatrice", "ouvre le programme (après un « oui »)"),
        ("lance Inkscape", "même chose avec un autre programme"),
        ("ajoute l'application Bloc-notes C:\\Windows\\notepad.exe", "ajoute un programme absent du menu"),
        ("ferme le programme", "ferme un programme de la liste autorisée, après confirmation")]),
    "sauvegarde": ("Sauvegarde", "Copie vos données dans un fichier zip.", [
        ("sauvegarde", "crée une sauvegarde dans le dossier prévu")]),
    "ordinateur": ("Ordinateur", "État de la machine et journal des dernières actions.", [
        ("comment va l'ordinateur", "donne l'état du processeur, de la mémoire et du disque"),
        ("qu'as-tu fait", "affiche le journal des dernières actions")]),
    "heure": ("Heure et date", "L'heure et la date du jour.", [
        ("quelle heure est-il", "donne l'heure"),
        ("quel jour sommes-nous", "donne la date")]),
    "calcul": ("Calculatrice (skill « calcul »)", "Calculs exacts. À installer : « installe skill calcul ».", [
        ("combien font 17 pour cent de 2350", "donne le résultat exact"),
        ("calcule 3 virgule 5 fois 2", "accepte les mots parlés"),
        ("combien font racine de 16", "racine carrée")]),
    "labo": ("Laboratoire en texte", "Chute libre, pendule, tir et pH, avec les formules simples.", [
        ("laboratoire chute 20 mètres", "temps et vitesse de chute sans frottement"),
        ("laboratoire pendule 1 mètre", "période du pendule"),
        ("laboratoire tir 20 mètres par seconde 45 degrés", "portée et hauteur"),
        ("laboratoire acide 0,01", "pH d'un acide fort"),
        ("laboratoire ressort masse 2 raideur 50 amortissement 1", "période et amortissement d'un ressort"),
        ("laboratoire circuit 1000 0,001 5", "charge d'un condensateur (constante de temps RC)"),
        ("laboratoire réfraction 30 degrés air eau", "angle transmis entre deux milieux (loi de Snell)"),
        ("convertis 100 km/h en m/s", "conversion d'unités (vitesse, longueur, masse, volume, température)")]),
    "labo3d": ("Laboratoire 3D (skill « labo3d »)", "Simulations en 3D dans le navigateur, avec frottement de l'air. À installer : « installe skill labo3d ».", [
        ("labo 3d chute de 20 mètres", "ouvre la chute dans le navigateur"),
        ("labo 3d pendule 1,5 mètres 60 degrés", "ouvre le pendule"),
        ("labo 3d tir 40 mètres par seconde 45 degrés", "ouvre le tir, avec et sans air"),
        ("labo 3d pendule 1 mètre 30 degrés", "ouvre le pendule, avec son graphique d'énergie"),
        ("propose labo pendule", "propose la simulation et attend votre « oui » avant de l'ouvrir")]),
    "situations": ("Simulateur de situations", "Des scénarios de décision avec des conseils.", [
        ("simulation", "lance un scénario au hasard"),
        ("situation panne", "lance le scénario de panne de carburant")]),
    "meteo": ("Météo (Internet)", "Température actuelle pour votre ville. Demande l'accès Internet.", [
        ("météo", "donne la température. Sans accès : « active internet météo »")]),
    "loisirs": ("Blagues, échecs, jeux, YouTube", "Quelques distractions.", [
        ("raconte une blague", "dit une blague"),
        ("échecs", "lance une partie"),
        ("joue à minecraft", "lance le jeu configuré dans config.json"),
        ("youtube chats drôles", "ouvre une recherche YouTube (Internet requis)")]),
    "communication": ("Appels et WhatsApp", "Appels via votre téléphone Android (adb) et messages WhatsApp. Confirmation à chaque envoi.", [
        ("appelle Marc", "appelle le numéro enregistré (skill « appel »)"),
        ("whatsapp à Marc dis lui que je suis en route", "envoie le message après « oui » (skill « whatsapp », Internet requis)")]),
    "internet": ("Accès Internet", "Internet est coupé par défaut. Chaque service s'autorise séparément.", [
        ("active internet whatsapp", "autorise WhatsApp après confirmation"),
        ("désactive internet whatsapp", "coupe l'accès")]),
    "skills": ("Skills", "Des fonctions installables, et vos propres réponses (recettes).", [
        ("installe skill calcul", "installe la calculatrice"),
        ("désinstalle skill calcul", "retire une fonction"),
        ("mes skills", "liste les skills disponibles et installés"),
        ("crée skill salut | bonjour, salut | Bonjour Michael !", "crée une réponse personnalisée")]),
    "idees": ("Idées et avis", "Des pistes variées, ou un avis motivé. Sur les sujets sensibles, KITT présente les arguments des deux côtés.", [
        ("donne-moi des idées pour un cadeau d'anniversaire", "trois à cinq pistes, avec avantage et inconvénient"),
        ("que penses-tu de Linux pour un vieil ordinateur", "un avis, présenté comme un point de vue"),
        ("désactive les idées", "KITT garde ses idées spontanées pour lui")]),
    "habitudes": ("Habitudes et initiatives", "KITT apprend vos sessions et signale les situations utiles (pause, batterie, heure tardive).", [
        ("mes habitudes", "montre ce qu'il a appris"),
        ("désactive les initiatives", "il ne prend plus la parole de lui-même"),
        ("active les initiatives", "il reprend ses signalements")]),
}

ALIAS = {"agenda": "agenda", "rendez-vous": "agenda", "rdv": "agenda", "tache": "taches", "tâche": "taches",
         "tâches": "taches", "taches": "taches", "note": "taches", "notes": "taches",
         "minuteur": "rappels", "minuteurs": "rappels", "contact": "contacts", "contacts": "contacts",
         "memoire": "memoire", "mémoire": "memoire", "souvenir": "memoire", "conversation": "conversations",
         "fichier": "fichiers", "fichiers": "fichiers", "lecture": "fichiers", "rédaction": "redaction",
         "redaction": "redaction", "rediger": "redaction", "email": "redaction", "mail": "redaction",
         "application": "applications", "applications": "applications", "programme": "applications",
         "sauvegarde": "sauvegarde", "ordinateur": "ordinateur", "heure": "heure", "date": "heure",
         "calcul": "calcul", "calculatrice": "calcul", "labo": "labo", "laboratoire": "labo",
         "labo3d": "labo3d", "3d": "labo3d", "simulation": "situations", "situation": "situations",
         "météo": "meteo", "meteo": "meteo", "blague": "loisirs", "echecs": "loisirs", "échecs": "loisirs",
         "jeux": "loisirs", "jeu": "loisirs", "youtube": "loisirs", "appel": "communication",
         "whatsapp": "communication", "internet": "internet", "skill": "skills", "skills": "skills",
         "habitudes": "habitudes", "initiatives": "habitudes", "idee": "idees", "idees": "idees",
         "idée": "idees", "idées": "idees", "avis": "idees"}


def sommaire():
    lignes = ["Voici ce que je sais faire, Michael. Dites « aide » suivi d'un thème pour le détail :"]
    lignes += [f"- {titre} (aide {cle})" for cle, (titre, _r, _c) in THEMES.items()]
    lignes.append("Dites par exemple : aide agenda, aide calcul, aide labo 3d.")
    return "\n".join(lignes)


def detail(cle):
    titre, resume, commandes = THEMES[cle]
    lignes = [f"{titre} : {resume}"]
    lignes += [f"- « {ex} » : {effet}" for ex, effet in commandes]
    return "\n".join(lignes)


def reponse(texte):
    """Repond a « aide ... » : sommaire, ou detail d'un theme cite dans la phrase."""
    n = sec.normaliser(texte)
    mots = n.replace(",", " ").replace("?", " ").split()
    if "3d" in mots or "labo3d" in mots or "labo 3d" in n:     # « 3d » est plus precis que « labo »
        return detail("labo3d")
    for mot in mots:
        cle = ALIAS.get(mot)
        if cle is None and mot in THEMES:
            cle = mot
        if cle:
            return detail(cle)
    return sommaire()
