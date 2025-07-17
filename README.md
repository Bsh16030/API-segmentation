# API d'Analyse Audio Porcin - Guide Technique

Ce document est un guide rapide pour installer, lancer et utiliser l'API d'analyse.

---

## 1. Installation

**Prérequis :** Python 3.9+, Git

1.  **Cloner le Dépôt**
    ```bash
    git clone git clone https://github.com/Bsh16030/API-segmentation.git
    cd API-segmentation
    ```

2.  **Créer et Activer l'Environnement Virtuel**
    ```bash
    # Créer
    python -m venv venv
    # Activer (Windows PowerShell)
    .\venv\Scripts\Activate.ps1
    ```

3.  **Installer les Dépendances**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configurer les Identifiants**
    * Créez un fichier `.env` à la racine.
    * Ajoutez et complétez les variables :
        ```env
        AIDB_HOST="[https://dbagoranov.bimea.tech](https://dbagoranov.bimea.tech)"
        AIDB_LOGIN="votre_login"
        AIDB_PASSWORD="votre_mot_de_passe"
        ```

---

## 2. Lancement du Serveur

* **Développement :**
    ```bash
    uvicorn serveur_api_flexible:app --reload --port 8001
    ```
* **Production (recommandé) :**
    ```bash
    gunicorn -w 4 -k uvicorn.workers.UvicornWorker serveur_api_flexible:app -b 0.0.0.0:8001
    ```

L'API sera accessible sur `http://<ip_du_serveur>:8001`. La documentation interactive est disponible sur `/docs`.

---

## 3. Endpoint d'Analyse

### `POST /analyze/{audio_id}`

Lance une analyse sur un fichier audio.

#### **Paramètres de l'Analyse (Corps de la requête en `Form Data`)**

| Paramètre          | Type      | Défaut | Description                               |
| :----------------- | :-------- | :----- | :---------------------------------------- |
| `seuil_pct`        | `integer` | `70`   | Seuil de détection des segments (1-99).   |
| `duree_buffer`     | `float`   | `1.0`  | Marge en secondes autour des segments.    |
| `debut_bruit`      | `float`   | `2.0`  | Début (s) de la prise de profil de bruit. |
| `fin_bruit`        | `float`   | `5.0`  | Fin (s) de la prise de profil de bruit.   |
| `facteur_reduction`| `float`   | `1.5`  | Agressivité de la réduction de bruit.     |

#### **Options de Réponse (Paramètres de l'URL)**

| Paramètre                | Type      | Défaut | Description                                |
| :----------------------- | :-------- | :----- | :----------------------------------------- |
| `include_plot`           | `boolean` | `True` | Inclut le graphique dans la réponse.       |
| `include_audio_clips`    | `boolean` | `False`| Inclut les extraits audio (lourd).         |
| `include_classification` | `boolean` | `True` | Inclut la classification Truie/Porcelet.   |

---

## 4. Structure de la Réponse JSON

Voici un exemple de la réponse **la plus complète possible** (avec toutes les options activées). Certains champs seront `null` si les options correspondantes sont à `false`.

```json
{
  "message": "2 segments trouvés et classifiés.",
  "audio_filename": "sourcefile_8.wav",
  "total_duration_seconds": 900.0,
  "plot_image_base64": "iVBORw0KGgoAAAANSUhEUgA... (longue chaîne de caractères pour l'image PNG)",
  "segments": [
    {
      "segment_number": 1,
      "start_time_seconds": 45.3,
      "end_time_seconds": 47.8,
      "predicted_animal_type": "Porcelet"
    },
    {
      "segment_number": 2,
      "start_time_seconds": 121.1,
      "end_time_seconds": 122.5,
      "predicted_animal_type": "Truie"
    }
  ],
  "full_segments_details": [
    {
      "segment_number": 1,
      "start_time_seconds": 45.3,
      "end_time_seconds": 47.8,
      "predicted_animal_type": "Porcelet",
      "audio_base64": "UklGRiQAAABXQVZFZm... (longue chaîne de caractères pour l'audio WAV)"
    },
    {
      "segment_number": 2,
      "start_time_seconds": 121.1,
      "end_time_seconds": 122.5,
      "predicted_animal_type": "Truie",
      "audio_base64": "UklGRiQAAABXQVZFZm..."
    }
  ]
}
```

#### **Description des Champs de la Réponse**

| Clé JSON                | Type    | Description                                                                    |
| :---------------------- | :------ | :----------------------------------------------------------------------------- |
| `message`               | `string`  | Un résumé textuel du résultat de l'analyse.                                    |
| `audio_filename`        | `string`  | Le nom du fichier audio original analysé.                                      |
| `total_duration_seconds`| `float`   | La durée totale en secondes de l'audio.                                        |
| `plot_image_base64`     | `string` ou `null` | L'image du graphique encodée en Base64. `null` si `include_plot=false`. |
| `segments`              | `array`   | Une liste d'objets, contenant toujours les timings et la classification (si demandée). |
| `full_segments_details` | `array` ou `null` | Une liste complète incluant les extraits audio en Base64. Ce champ n'est présent et rempli que si `include_audio_clips=true`. |

