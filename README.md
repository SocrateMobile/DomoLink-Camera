# DomoLink-Camera 📹

Intégration personnalisée Home Assistant pour la gestion centralisée et le streaming en direct des caméras Wi-Fi (YsxLite, A9, X5, PPPP, RTSP, ONVIF).

---

## 🌟 Fonctionnalités

- **Panneau latéral dédié** dans Home Assistant avec thème sombre/verre reprenant les codes graphiques de **DomoLink-Alarm**.
- **Grille de vignettes interactives** :
  - Affichage par défaut de la dernière prise de vue (snapshot).
  - Bouton **Live** pour basculer instantanément en flux vidéo temps réel.
  - **Drag & Drop** fluide pour réorganiser l'ordre des caméras à votre convenance.
  - Bouton flottant dynamique **« Sauvegarder l'ordre »** dès qu'une vignette est déplacée.
  - **Rollover descriptif** : affichage au survol de la souris d'une description personnalisée et de l'adresse IP.
  - **Bandeau bas interactif** : liaison avec vos entités Home Assistant (lumière de la pièce, capteur de mouvement, ouverture de porte, température) avec bascule directe d'un clic !
- **Onglet Paramètres complet** :
  - **Assistant d'appairage Wi-Fi autonome** (sans passer par une application mobile).
  - Scanner réseau local UDP (port `32108`) pour détecter automatiquement les caméras.
  - Renommage, modification des descriptions, assignation d'entités et suppression.
- **Architecture modulaire extensible** :
  - Pilote natif **YsxLite / iLnk / PPPP** (UDP 32108, H.264 / MJPEG, IR Night Vision).
  - Pilote **RTSP / ONVIF / HTTP** pour caméras IP standards et webcams ESP32.

---

## 📦 Installation

### Méthode 1 : Via HACS (Dépôt personnalisé)
1. Ouvrez **HACS** > **Intégrations**.
2. Cliquez sur les trois points en haut à droite > **Dépôts personnalisés**.
3. Ajoutez l'URL de votre dépôt avec la catégorie **Intégration**.
4. Téléchargez et redémarrez Home Assistant.

### Méthode 2 : Installation manuelle
Copiez le dossier `custom_components/domolink_camera` dans le dossier `custom_components/` de votre configuration Home Assistant, puis redémarrez Home Assistant.

---

## 🚀 Configuration
1. Dans Home Assistant : **Paramètres** > **Appareils et services** > **Ajouter une intégration** > **DomoLink-Camera**.
2. Cliquez sur l'onglet **DomoLink Camera** dans le panneau latéral gauche.
3. Rendez-vous dans l'onglet **Paramètres & Appairage** pour associer ou ajouter vos caméras !
