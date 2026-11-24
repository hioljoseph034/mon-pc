"""Mesure la fiabilite du modele local sur un petit jeu de questions a reponse connue.

Usage (Ollama doit tourner) :
    python evaluer_modele.py                 # modele de config.json
    python evaluer_modele.py mistral         # modele donne
Les questions sont dans kitt_fiabilite.CAS_REFERENCE. Pour ajouter un cas, ajoutez un dictionnaire
avec « question », « doit » (mots attendus) et, si besoin, « interdit » (mots qui ne doivent pas apparaitre).
"""
import sys

import kitt_complet as K
import kitt_fiabilite as F
import kitt_securite as sec


def main():
    modele = sys.argv[1] if len(sys.argv) > 1 else sec.charger_config()["modele_llm"]

    def produire(systeme, consigne):
        return K._appeler(systeme, consigne, modele, 60, 120, None)

    reussis, total, echecs = F.evaluer(produire, F.CAS_REFERENCE)
    print(f"Modèle {modele} : {reussis}/{total} réponses correctes.")
    for question, reponse in echecs:
        print(f"  - Échec : {question}\n    Réponse : {reponse[:200]}")


if __name__ == "__main__":
    main()
