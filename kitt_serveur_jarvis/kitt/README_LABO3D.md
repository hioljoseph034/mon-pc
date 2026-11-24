# KITT — Laboratoire 3D

Ce guide explique comment installer et utiliser la simulation 3D du laboratoire de KITT.
La simulation s'ouvre dans votre navigateur, sous forme d'un fichier HTML autonome. Aucune connexion Internet n'est nécessaire pour l'afficher.

---

## 1. Installer le skill

Le laboratoire 3D est un skill installable. Dites (ou tapez) :

```
installe skill labo3d
```

Vous devez obtenir : « Skill « labo3d » installé : Laboratoire 3D (simulation dans le navigateur). »

Pour le retirer : `désinstalle skill labo3d`.

## 2. Lancer une simulation

Trois scénarios sont disponibles. Les nombres se donnent dans l'ordre indiqué, avec ou sans unités.

| Scénario | Commande | Paramètres (valeur par défaut) |
|---|---|---|
| Chute libre | `labo 3d chute de 20 mètres` | hauteur en mètres (10) |
| Pendule | `labo 3d pendule 1,5 mètres 60 degrés` | longueur en mètres (1), angle d'écart en degrés (30) |
| Tir de projectile | `labo 3d tir 40 mètres par seconde 45 degrés` | vitesse en m/s (20), angle en degrés (45) |

Les mots « simulation 3d », « simule en 3d » et « en 3d » fonctionnent aussi.
Une commande sans scénario reçoit la réponse : « Quelle simulation ? Dites : labo 3d chute, labo 3d pendule ou labo 3d tir. »

KITT répond à voix haute avec une première donnée chiffrée (par exemple la période du pendule), puis ouvre la page.

## 3. Utiliser la fenêtre de simulation

- **Faire tourner la scène** : cliquez-glissez avec la souris.
- **Zoomer et dézoomer** : molette de la souris.
- **Lecture / pause** : bouton « Lecture / pause ».
- **Recommencer** : bouton « Recommencer ».
- **Axes** : rouge = horizontal, vert = vertical, bleu = profondeur. Le quadrillage représente le sol (ou le niveau du pivot pour le pendule).

Les informations chiffrées s'affichent en haut de la page, à côté des boutons.

## 4. Ce que calcule chaque scénario

**Chute libre** : la personne (70 kg, surface de 0,7 m²) tombe avec le frottement de l'air. La page affiche le temps de chute sans air et avec air, la vitesse à l'impact et la vitesse limite, c'est-à-dire la vitesse maximale atteinte en régime permanent.

**Pendule** : la période est calculée exactement, pas seulement avec la formule simple « 2π√(L/g) ». Pour de petits angles, les deux valeurs sont presque identiques. À 60°, la période réelle est environ 7 % plus longue. La page indique l'écart en pourcentage.

**Tir de projectile** : une balle de baseball (145 g, rayon 3,5 cm) est lancée avec le frottement de l'air. La page affiche deux trajectoires dans la même scène, « avec l'air » et « sans air », pour les comparer, ainsi que la portée et la hauteur maximale.

**Graphique de l'énergie (pendule)** : sous la scène, un graphique montre l'énergie cinétique, l'énergie potentielle et l'énergie totale, par unité de masse. La courbe de l'énergie totale reste plate : c'est la conservation de l'énergie, et un bon moyen de vérifier la simulation.

**Proposer une simulation** : « propose labo pendule » (ou le geste « quatre doigts levés ») ne lance rien tout de suite. KITT demande d'abord « J'ouvre une simulation de pendule dans votre navigateur, vous confirmez ? », et la simulation ne s'ouvre qu'après votre « oui ».

## 5. Limites de paramètres

Les valeurs hors limites sont **ramenées à la limite la plus proche**, sans message d'avertissement.

| Scénario | Minimum | Maximum |
|---|---|---|
| Chute (hauteur) | 0,5 m | 500 m |
| Pendule (longueur) | 0,05 m | 20 m |
| Pendule (angle) | 1° | 175° |
| Tir (vitesse) | 1 m/s | 300 m/s |
| Tir (angle) | 1° | 89° |

Si vous demandez « labo 3d chute de 10000 mètres », la simulation affichera une chute de 500 m.

## 6. Où sont les fichiers

Chaque simulation crée un fichier numéroté dans :
- Windows : `C:\Users\VotreNom\.kitt\simulations\`
- Linux : `~/.kitt/simulations/`

Exemples : `chute_0001.html`, `pendule_0002.html`. Le dossier n'est jamais nettoyé automatiquement : supprimez manuellement les fichiers dont vous n'avez plus besoin. Les fichiers sont privés (droits 600 sous Linux et macOS).

Si le navigateur ne s'ouvre pas, ouvrez le fichier à la main : double-cliquez dessus dans le dossier ci-dessus.

## 7. Dépannage

| Problème | Solution |
|---|---|
| Rien ne s'ouvre | Ouvrez le fichier à la main depuis le dossier `simulations`. Sous Linux, vérifiez qu'un navigateur est installé par défaut. |
| « Quelle simulation ? » | Le scénario n'a pas été reconnu. Utilisez le mot exact : chute, pendule ou tir. |
| L'animation ne bouge pas | Cliquez sur « Lecture / pause ». Si la lecture est finie, « Recommencer » relance l'animation. |
| La page est vide | Le navigateur bloque peut-être le JavaScript. Autorisez-le pour ce fichier local. |
| Le skill n'existe pas | Installez-le avec `installe skill labo3d`. |
| Le laboratoire 2D répond au lieu de la 3D | Ajoutez « 3d » dans la phrase : « labo 3d chute ». Sans « 3d », c'est le laboratoire en texte qui répond. |

## 8. Limites connues

- Le rendu n'a pas été vérifié visuellement sur votre machine : le code est validé, mais l'animation reste à regarder.
- Les modèles sont simplifiés : pas de vent, pas de rotation de la balle, un seul coefficient de frottement par objet.
- Le pendule est plan (il oscille dans un seul plan). Le tir est dans un plan vertical.
- Les valeurs hors limites sont corrigées sans avertissement (voir section 5).

## 9. Vérifier l'installation

```
python -m unittest test_kitt -v
```

Les **206 tests** doivent réussir, dont ceux du laboratoire.
