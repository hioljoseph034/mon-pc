"""Ton de KITT : plusieurs formulations par situation, salutations selon le moment de la journee.

Chaque categorie a plusieurs phrases. KITT en choisit une au hasard, sans jamais repeter
la precedente de la meme categorie. Les champs absents sont remplaces par du vide au lieu
de faire planter la reponse.
"""
import random
from datetime import datetime

PHRASES = {
    "accueil_matin": ["Bonjour {prenom}. Systèmes en ligne, prêt pour la journée.",
                      "Bonjour {prenom}, je suis là. Par quoi on commence ?",
                      "Bien dormi, {prenom} ? Je suis opérationnel."],
    "accueil_apresmidi": ["Bon après-midi {prenom}. Tout est en ordre de mon côté.",
                          "Hé {prenom}, je suis à votre service.",
                          "Bonjour {prenom}. Une question, un rappel, un message ?"],
    "accueil_soir": ["Bonsoir {prenom}. Je suis toujours là.",
                     "Bonsoir {prenom}. Qu'est-ce qu'on fait ce soir ?",
                     "Bonsoir. La journée a été longue ? Je vous écoute."],
    "accueil_nuit": ["Il est tard, {prenom}. Vous devriez peut-être dormir.",
                     "Toujours debout à cette heure ? Je veille, {prenom}.",
                     "Il fait nuit, {prenom}. Dites-moi ce qui vous occupe."],
    "inconnu": ["Je ne connais pas encore cette commande. Vous pouvez m'apprendre : "
                "« apprends que ... veut dire ... ».",
                "Hmm, ça je ne sais pas faire encore, {prenom}. Reformulez, ou apprenez-moi.",
                "Je n'ai pas de module pour ça. Je suis un élève, mais je progresse.",
                "Désolé, cette demande me dépasse pour l'instant."],
    "pas_compris": ["Je n'ai pas compris.", "Pardon, je n'ai pas saisi. Vous pouvez répéter ?",
                    "Je n'ai pas bien entendu."],
    "blague_intro": ["Une blague pour vous, {prenom} :", "Allez, celle-ci :",
                     "Vous voulez rire ? Écoutez ça :", "Bon, une petite pour détendre l'atmosphère :"],
    "echecs": ["Échiquier prêt, {prenom}. Je ne perds jamais.",
               "Les pièces sont en place, {prenom}. Vous commencez ?",
               "Partie lancée. Je prends les noirs, si ça vous va.",
               "Échecs ? Bonne idée. Je suis en forme aujourd'hui."],
    "meteo_ville": ["À {ville} il fait {temp} degrés en ce moment, {prenom}. {conseil}",
                    "Il fait {temp} degrés à {ville}. {conseil}",
                    "{temp} degrés à {ville} pour le moment. {conseil}"],
    "meteo_frais": ["Prenez un pull, il fait frais.", "Un petit gilet ne ferait pas de mal."],
    "meteo_chaud": ["Pensez à boire, il fait chaud.", "Gardez de l'eau à portée de main."],
    "meteo_doux": ["Temps parfait pour rouler en Trans Am.", "Idéal pour une balade en voiture."],
    "jeu_lance": ["{nom} est lancé. Bon jeu, {prenom} !", "C'est parti pour {nom} ! Amusez-vous bien.",
                  "{nom} démarre. TURBO BOOST !"],
    "appel_ok": ["J'appelle {contact} au {numero}.", "Je compose le numéro de {contact}, un instant.",
                 "Appel en cours vers {contact}."],
    "whatsapp_ok": ["Message transmis à WhatsApp Web pour {contact}. Vérifiez qu'il est bien parti.",
                    "C'est envoyé vers WhatsApp Web pour {contact}. Je ne peux pas confirmer la réception."],
    "annule": ["D'accord, je ne fais rien.", "Très bien, j'annule.", "Pas de souci, rien n'est envoyé."],
    "pause": ["{prenom}, vous travaillez depuis {minutes} minutes. Une courte pause vous ferait du bien.",
              "Ça fait {minutes} minutes sans interruption, {prenom}. Et si on respirait un peu ?",
              "{minutes} minutes de concentration, bravo. Une pause de cinq minutes, maintenant ?"],
    "batterie": ["Batterie à {niveau} pour cent, {prenom}. Branchez le chargeur, je préfère éviter une coupure.",
                 "Il ne reste que {niveau} pour cent de batterie. Pensez au chargeur."],
    "tard": ["Il est {heure}, {prenom}. Vous devriez songer à dormir.",
             "{heure} déjà. Le travail peut attendre demain, {prenom}."],
    "disque": ["Il ne reste que {libre} pour cent d'espace disque. Un peu de ménage serait utile.",
               "Attention, le disque est presque plein : {libre} pour cent libres."],
    "taches": ["Vous avez {nombre} tâches en attente, {prenom}. Dites « mes tâches » pour les voir.",
               "{nombre} tâches ouvertes. Dites « mes tâches » si vous voulez faire le point."],
    "confirme": ["Dites oui ou non.", "Vous confirmez ? Dites oui ou non.",
                 "Oui ou non ?"],
    "confirme_chaleureux": ["Vous êtes d'accord ? Dites oui ou non, je ne bouge pas sans votre accord.",
                            "Dites oui si vous voulez que je le fasse, non sinon."],
    "confirme_espiegle": ["Feu vert ou feu rouge ? Oui ou non.", "Je vous écoute : oui ou non ?"],
    "app_introuvable": ["Je ne trouve pas « {nom} » parmi vos applications. Dites : ajoute l'application "
                        "{nom} suivi du chemin du programme.",
                        "« {nom} » n'est pas dans le menu Démarrer. Donnez-moi son chemin complet et je l'enregistre."],
    "app_introuvable_chaleureux": ["Je ne trouve pas « {nom} » sur cet ordinateur. Si vous me donnez son chemin "
                                   "complet, je l'ajoute et je l'ouvrirai la prochaine fois."],
    "app_introuvable_espiegle": ["« {nom} » se cache bien ! Donnez-moi son chemin complet et je le retrouve."],
    "sans_numero": ["Je ne trouve aucun contact avec un numéro. Dites : ajoute le numéro de Marc "
                    "06 77 12 34 56, et je m'en servirai.",
                    "Il me manque un numéro pour ce contact. Dites : ajoute le numéro de Marc suivi du numéro."],
    "sans_numero_chaleureux": ["Je ne connais pas encore le numéro de ce contact. Dites-le-moi, par exemple : "
                               "ajoute le numéro de Marc 06 77 12 34 56, et c'est fait."],
    "reseau_requis": ["{service} demande Internet. Dites : active internet {service}, je m'en occupe ensuite.",
                      "Il me faut l'accès Internet pour {service}. Dites « active internet {service} » et je "
                      "vous donne la réponse."],
    "reseau_requis_chaleureux": ["Pour {service}, j'ai besoin d'Internet. Autorisez-le d'un mot : "
                                 "« active internet {service} »."],
    "labo3d_aucun": ["Quelle simulation voulez-vous ? Chute, pendule ou tir : dites par exemple « labo 3d pendule ».",
                     "Je peux simuler une chute, un pendule ou un tir. Lequel ? Par exemple : labo 3d tir."],
    "youtube_ok": ["YouTube est ouvert sur « {recherche} ».", "Je lance la recherche « {recherche} » sur YouTube."],
}


class _Vide(dict):
    """Un champ absent devient du texte vide au lieu de lever une erreur."""
    def __missing__(self, cle):
        return ""


_derniers = {}
TONS = ("sobre", "chaleureux", "espiegle")


def ton_courant():
    """Ton choisi dans config.json (« ton »). Sobre si la configuration est illisible."""
    try:
        import kitt_securite as sec
        return sec.charger_config().get("ton", "chaleureux")
    except Exception:
        return "sobre"


def phrase(categorie, **champs):
    """Une formulation de la categorie, differente de la precedente de cette categorie.
    Si une variante existe pour le ton choisi (« categorie_chaleureux »), elle est utilisee."""
    ton = ton_courant()
    cle = categorie
    if ton in TONS and ton != "sobre" and f"{categorie}_{ton}" in PHRASES:
        cle = f"{categorie}_{ton}"
    pool = PHRASES[cle]
    if len(pool) == 1:
        choix = 0
    else:
        choix = random.randrange(len(pool))
        while choix == _derniers.get(cle):
            choix = random.randrange(len(pool))
    _derniers[cle] = choix
    return pool[choix].format_map(_Vide(champs)).strip()


def moment(heure=None):
    h = datetime.now().hour if heure is None else heure
    if 5 <= h < 12:
        return "matin"
    if 12 <= h < 18:
        return "apresmidi"
    if 18 <= h < 23:
        return "soir"
    return "nuit"


def accueil(prenom, heure=None):
    return phrase(f"accueil_{moment(heure)}", prenom=prenom)


def conseil_meteo(temp):
    if temp <= 20:
        return phrase("meteo_frais")
    if temp >= 32:
        return phrase("meteo_chaud")
    return phrase("meteo_doux")
