# Raspberry Pi Controller (OSC to GPIO)

Le contrôleur Raspberry Pi (`rpi-controller`) écoute en permanence les messages réseau OSC envoyés par l'interface d'administration et les traduit en signaux électriques (PWM).

## 1. Protocole OSC

Le script Python embarqué démarre un serveur UDP OSC avec les caractéristiques suivantes :

- **Port d'écoute :** `9000` (configurable dans `config.py`)
- **Adresses supportées :**
  - `/gpio/a` : Contrôle le canal A
  - `/gpio/b` : Contrôle le canal B
- **Valeurs attendues :** Un nombre flottant (`float`) compris entre `0.0` et `1.0`. 
  - `0.0` = Arrêt complet (0%)
  - `1.0` = Vitesse maximale (100%)

*(Toute valeur en dehors de la plage 0.0 - 1.0 est automatiquement bridée par le script).*

## 2. Installation et Lancement

Le déploiement sur le Raspberry Pi est entièrement automatisé par le script `install.sh`. 

### Pré-requis sur le Raspberry Pi :
- Raspberry Pi OS installé
- Un accès SSH ou terminal
- Connexion réseau fonctionnelle

### Procédure :
1. Copiez le dossier `rpi-controller` sur le Raspberry Pi.
2. Connectez-vous en SSH et exécutez le script d'installation :
   ```bash
   sudo bash install.sh
   ```

### Que fait le script d'installation ?
1. Il crée un dossier dédié dans `/opt/gpio-osc/`.
2. Il initialise un environnement virtuel Python (`venv`) et installe les dépendances.
3. Il crée et active un service **systemd** nommé `gpio-osc.service`.

Grâce à `systemd`, le contrôleur OSC démarre automatiquement dès l'allumage du Raspberry Pi, et redémarre tout seul en cas de problème.

### Commandes utiles (sur le Raspberry Pi)
- Vérifier l'état du service : `systemctl status gpio-osc`
- Lire les logs en temps réel : `journalctl -u gpio-osc -f`
- Relancer manuellement : `sudo systemctl restart gpio-osc`
- Stopper le service : `sudo systemctl stop gpio-osc`