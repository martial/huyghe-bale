# Raspberry Pi Controller (OSC to GPIO)

Le contrôleur Raspberry Pi (`rpi-controller`) est le composant matériel du projet Pierre Huyghe Bâle. Il écoute en permanence les messages réseau OSC envoyés par l'interface d'administration (Mac) et les traduit instantanément en signaux électriques (PWM) pour piloter un contrôleur de moteurs L298N (qui gère par exemple des ventilateurs ou des moteurs DC).

## 1. Protocole OSC

Le script Python embarqué démarre un serveur UDP OSC avec les caractéristiques suivantes :

- **Port d'écoute :** `9000` (défini dans `config.py`)
- **Adresses supportées :**
  - `/gpio/a` : Contrôle le canal A (Moteur A)
  - `/gpio/b` : Contrôle le canal B (Moteur B)
- **Valeurs attendues :** Un nombre flottant (`float`) compris entre `0.0` et `1.0`. 
  - `0.0` correspond à un arrêt complet (Duty cycle 0%)
  - `1.0` correspond à la vitesse maximale (Duty cycle 100%)

*Note : Toute valeur en dehors de la plage 0.0 - 1.0 est automatiquement bridée (clamped) par le script.*

## 2. Câblage et Hardware (L298N)

Le script utilise la librairie `RPi.GPIO` en mode BCM. La fréquence PWM par défaut est de **1000 Hz**.
La direction de rotation est **fixée en marche avant** au démarrage du script (impossible d'inverser le sens via OSC dans cette version).

### Correspondance des broches (Pins BCM)

| Fonction L298N | Pin BCM Raspberry | État / Explication |
| :--- | :--- | :--- |
| **ENA** (Vitesse Moteur A) | `GPIO 12` | Signal PWM (0 à 100%) via la commande `/gpio/a` |
| **ENB** (Vitesse Moteur B) | `GPIO 13` | Signal PWM (0 à 100%) via la commande `/gpio/b` |
| **IN1** (Direction A 1) | `GPIO 5` | Bloqué sur **HIGH** (Marche avant) |
| **IN2** (Direction A 2) | `GPIO 6` | Bloqué sur **LOW** |
| **IN3** (Direction B 1) | `GPIO 16` | Bloqué sur **HIGH** (Marche avant) |
| **IN4** (Direction B 2) | `GPIO 20` | Bloqué sur **LOW** |

## 3. Installation et Lancement

Le déploiement sur le Raspberry Pi est entièrement automatisé par le script `install.sh`. 

### Pré-requis sur le Raspberry Pi :
- Raspberry Pi OS installé
- Un accès SSH ou terminal
- Connexion réseau sur le même sous-réseau que le Mac (Admin)

### Procédure :
1. Copier le dossier `rpi-controller` sur le Raspberry Pi.
2. Exécuter le script d'installation avec les droits administrateur :
   ```bash
   sudo bash install.sh
   ```

### Que fait le script d'installation ?
1. Il crée un dossier dédié dans `/opt/gpio-osc/`.
2. Il initialise un environnement virtuel Python (`venv`) autonome pour ne pas polluer le système.
3. Il installe les dépendances nécessaires (`python-osc`, `RPi.GPIO`, `requests`).
4. Il copie les scripts `gpio_osc.py` et `config.py`.
5. Il crée et active un service **systemd** nommé `gpio-osc.service`.

Grâce à `systemd`, le script OSC démarre automatiquement dès l'allumage du Raspberry Pi, fonctionne en tâche de fond, et redémarre tout seul en cas de plantage.

### Commandes utiles (sur le Raspberry Pi)
- Vérifier l'état du service : `systemctl status gpio-osc`
- Lire les logs en temps réel : `journalctl -u gpio-osc -f`
- Relancer manuellement le service : `sudo systemctl restart gpio-osc`
- Stopper le service (arrête les moteurs) : `sudo systemctl stop gpio-osc`

## 4. Fonctionnalité avancée : Webhooks

Le contrôleur intègre un système optionnel de **Webhooks** (via le fichier `webhooks.json`). 
Cela permet au Raspberry Pi d'envoyer des requêtes HTTP (POST) à d'autres services ou API lorsqu'un événement se produit, sans bloquer la réception des messages OSC.

Les événements disponibles sont :
- `start` : Au lancement du service
- `stop` : À l'arrêt du service
- `change` : À chaque fois qu'une valeur OSC est reçue pour le canal A ou B (avec la valeur en charge utile).

*Si le fichier `webhooks.json` est absent ou mal formaté, la fonctionnalité est simplement ignorée.*