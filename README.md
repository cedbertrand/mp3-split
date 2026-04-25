# 🎵 split_album.py — Découpeur de fichiers MP3 avec balises ID3

> Découpe un fichier MP3 album en pistes individuelles et y intègre automatiquement les métadonnées ID3 (titre, artiste, pochette, etc.) depuis des fichiers de métadonnées Internet Archive.

---

## Table des matières

- [Description](#description)
- [Fonctionnement](#fonctionnement)
- [Prérequis système](#prérequis-système)
- [Installation dans un environnement virtuel](#installation-dans-un-environnement-virtuel)
- [Paramètres](#paramètres)
- [Exemple d'utilisation](#exemple-dutilisation)
- [Structure de sortie](#structure-de-sortie)
- [Format des fichiers de métadonnées](#format-des-fichiers-de-métadonnées)
- [Remarques et limitations](#remarques-et-limitations)
- [Dépannage](#dépannage)

---

## Description

`split_album.py` est un script Python en ligne de commande qui permet de **découper un fichier MP3 contenant un album complet** (toutes les pistes à la suite) en autant de fichiers MP3 individuels que l'album compte de morceaux.

Chaque fichier généré est automatiquement enrichi de **balises ID3v2** :

| Balise | Contenu |
|--------|---------|
| `TIT2` | Titre de la piste |
| `TPE1` | Artiste / groupe |
| `TALB` | Titre de l'album |
| `TDRC` | Année de publication |
| `TRCK` | Numéro de piste (ex. `3/10`) |
| `TCON` | Genre(s) musical(aux) |
| `TPUB` | Label / éditeur |
| `APIC` | Image de couverture (pochette) |

Les métadonnées sont lues depuis un fichier **XML** et/ou **SQLite** au format [Internet Archive](https://archive.org), qui accompagnent généralement les téléchargements effectués depuis cette plateforme.

---

## Fonctionnement

Le script opère en quatre étapes successives :

### 1️⃣ Lecture des métadonnées

Le fichier XML (prioritaire) est analysé pour en extraire : artiste, titre de l'album, année, label, genre(s), et la **tracklist complète** (titres + durées) encodée en HTML dans le champ `<description>` du XML. Le fichier SQLite sert de fallback pour le titre si le XML est absent.

### 2️⃣ Calcul des points de découpe

À partir des durées de chaque piste (`MM:SS`), le script calcule les positions temporelles (en millisecondes) dans le MP3 source :

```
Piste 1 :     0 ms  →  74 000 ms  (01:14)
Piste 2 : 74 000 ms  → 335 000 ms  (04:21)
...
Piste N : position précédente  →  fin du fichier
```

> Le dernier morceau s'étend toujours jusqu'à la fin réelle du fichier afin d'absorber les éventuels décalages dus à l'encodage.

### 3️⃣ Découpage et export

Chaque segment est extrait et ré-encodé en **MP3 320 kbps** via [pydub](https://github.com/jiaaro/pydub) (qui s'appuie sur `ffmpeg` en interne). Le fichier est nommé : `NN - Titre de la piste.mp3`.

### 4️⃣ Écriture des balises ID3v2

Les balises listées dans la section [Description](#description) sont écrites dans chaque fichier MP3 généré, incluant la pochette si une image est fournie.

---

## Prérequis système

- **Python 3.10** ou supérieur

  ```bash
  python3 --version
  ```

- **ffmpeg** (requis par pydub pour décoder/encoder l'audio)

  | Système | Commande |
  |---------|----------|
  | Linux (Debian/Ubuntu) | `sudo apt update && sudo apt install ffmpeg` |
  | macOS (Homebrew) | `brew install ffmpeg` |
  | Windows | [Télécharger sur ffmpeg.org](https://ffmpeg.org/download.html) puis ajouter `bin/` au PATH |

  ```bash
  ffmpeg -version   # vérification
  ```

---

## Installation dans un environnement virtuel

### 1. Cloner ou télécharger le script

```bash
git clone https://github.com/cedbertrand/split-album.git
cd split-album
```

### 2. Créer l'environnement virtuel

```bash
python3 -m venv .venv
```

### 3. Activer l'environnement virtuel

```bash
# Linux / macOS
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (cmd.exe)
.venv\Scripts\activate.bat
```

> Votre invite de commande affichera `(.venv)` pour confirmer que l'environnement est actif.

### 4. Installer les dépendances Python

```bash
pip install pydub mutagen
```

| Bibliothèque | Rôle |
|--------------|------|
| `pydub` | Manipulation et découpage de fichiers audio |
| `mutagen` | Lecture et écriture de balises ID3 dans les fichiers MP3 |

### 5. Vérifier l'installation

```bash
pip list                         # pydub et mutagen doivent apparaître
python split_album.py --help     # affiche l'aide sans erreur
```

### 6. Désactiver l'environnement (en fin de session)

```bash
deactivate
```

---

## Paramètres

```
python split_album.py [options]
```

| Paramètre | Requis | Description |
|-----------|--------|-------------|
| `--mp3` | ✅ Oui | Chemin vers le fichier MP3 source (album complet) |
| `--xml` | ⚠️ Au moins l'un des deux | Fichier XML de métadonnées (format Internet Archive) |
| `--sqlite` | ⚠️ Au moins l'un des deux | Fichier SQLite de métadonnées (format Internet Archive) |
| `--cover` | ❌ Non | Image de pochette à intégrer dans les MP3 (JPG ou PNG) |
| `--outdir` | ❌ Non | Répertoire de base pour la sortie (défaut : répertoire courant) |

> **Note :** `--xml` est prioritaire pour toutes les métadonnées. `--sqlite` sert uniquement de fallback pour le titre. Il est recommandé de fournir les deux.

---

## Exemple d'utilisation

Supposons que vous disposiez des fichiers suivants pour l'album fictif **"Echoes of the Storm"** du groupe **"Northern Lights"** (sorti en 2003) :

```
echoes-of-the-storm/
├── northern-lights-echoes-of-the-storm.mp3       ← album complet
├── northern-lights-echoes-of-the-storm_meta.xml
├── northern-lights-echoes-of-the-storm_meta.sqlite
└── cover.jpg
```

<details>
<summary>Voir le contenu XML simplifié</summary>

```xml
<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <title>Echoes of the Storm</title>
  <creator>Northern Lights</creator>
  <date>2003-06-15</date>
  <label>Polar Records</label>
  <genre>progressive rock</genre>
  <genre>post-rock</genre>
  <runtime>48:30</runtime>
  <description>
    <!-- Tableau HTML avec la tracklist et les durées -->
  </description>
</metadata>
```

</details>

### Commandes

```bash
# 1. Se placer dans le dossier
cd echoes-of-the-storm/

# 2. Activer l'environnement virtuel
source /chemin/vers/.venv/bin/activate

# 3. Lancer le script
python split_album.py \
    --mp3     "northern-lights-echoes-of-the-storm.mp3" \
    --xml     "northern-lights-echoes-of-the-storm_meta.xml" \
    --sqlite  "northern-lights-echoes-of-the-storm_meta.sqlite" \
    --cover   "cover.jpg" \
    --outdir  "~/Musique"
```

### Sortie console

```
→ Lecture XML : northern-lights-echoes-of-the-storm_meta.xml
→ Lecture SQLite : northern-lights-echoes-of-the-storm_meta.sqlite

── Album : Echoes of the Storm (2003) ──
   Artiste : Northern Lights
   Label   : Polar Records
   Genre   : progressive rock; post-rock
   Pistes  : 8

→ Répertoire de sortie : ~/Musique/Northern Lights/Echoes of the Storm (2003)

→ Chargement de northern-lights-echoes-of-the-storm.mp3 …
  Durée totale : 48:30
  [01/08] Frozen Horizon (05:12)      →  01 - Frozen Horizon.mp3
  [02/08] The Wanderer (04:47)        →  02 - The Wanderer.mp3
  [03/08] Amber Skies (06:03)         →  03 - Amber Skies.mp3
  [04/08] Silent Current (03:58)      →  04 - Silent Current.mp3
  [05/08] Interlude (01:30)           →  05 - Interlude.mp3
  [06/08] Cascade (07:21)             →  06 - Cascade.mp3
  [07/08] Aftermath (05:44)           →  07 - Aftermath.mp3
  [08/08] Echoes of the Storm (13:55) →  08 - Echoes of the Storm.mp3

✓ 8 piste(s) exportée(s) dans : ~/Musique/Northern Lights/Echoes of the Storm (2003)
```

---

## Structure de sortie

```
<outdir>/
└── <Artiste>/                        ← nom du groupe ou de l'artiste
    └── <Album (Année)>/              ← titre de l'album + année
        ├── 01 - <Titre piste 1>.mp3
        ├── 02 - <Titre piste 2>.mp3
        └── ...
```

> Si le champ `<creator>` est absent du XML mais qu'une `<collection>` est renseignée, le nom de la collection est utilisé à la place de l'artiste.

**Exemple avec l'album fictif (outdir : `~/Musique`) :**

```
~/Musique/
└── Northern Lights/
    └── Echoes of the Storm (2003)/
        ├── 01 - Frozen Horizon.mp3
        ├── 02 - The Wanderer.mp3
        ├── 03 - Amber Skies.mp3
        ├── 04 - Silent Current.mp3
        ├── 05 - Interlude.mp3
        ├── 06 - Cascade.mp3
        ├── 07 - Aftermath.mp3
        └── 08 - Echoes of the Storm.mp3
```

---

## Format des fichiers de métadonnées

Le script est conçu pour les fichiers générés par [Internet Archive](https://archive.org) lors de l'upload d'un fichier audio.

### Fichier XML (`_meta.xml`)

| Balise XML | Contenu |
|------------|---------|
| `<title>` | Titre de l'album |
| `<creator>` | Artiste ou groupe |
| `<date>` | Date de parution (`YYYY-MM-DD` ou `YYYY`) |
| `<label>` | Label discographique |
| `<genre>` | Genre musical (peut apparaître plusieurs fois) |
| `<collection>` | Collection Internet Archive |
| `<language>` | Code langue (ex. `eng`) |
| `<runtime>` | Durée totale (`MM:SS`) |
| `<description>` | Contenu HTML avec la tracklist (parsée automatiquement) |

> La tracklist est extraite depuis le tableau HTML de la description. Chaque ligne doit contenir : **numéro · titre · durée** (`MM:SS`).

### Fichier SQLite (`_meta.sqlite`)

Base de données créée par le client d'upload d'Internet Archive. Le script interroge uniquement la table `s3api_per_key_metadata` pour extraire le titre de l'album en fallback si le XML est absent ou incomplet.

---

## Remarques et limitations

- **Précision du découpage** — Les points de coupure sont calculés à partir des durées déclarées (arrondies à la seconde). Un léger chevauchement ou silence entre pistes adjacentes est possible (< 1 s).

- **Qualité audio** — Le ré-encodage en MP3 320 kbps introduit une légère perte de qualité si le fichier source est déjà en MP3 (dégradation générationnelle). Pour des coupures sans ré-encodage, un outil DAW serait nécessaire.

- **Formats source** — Seul le MP3 est géré en entrée. Pour d'autres formats (FLAC, OGG, WAV), remplacez `AudioSegment.from_mp3()` par `AudioSegment.from_file()` dans le code.

- **Encodage des caractères** — Les noms de fichiers sont en UTF-8. Sur Windows, les chemins > 260 caractères peuvent nécessiter l'activation des chemins longs dans les paramètres système.

- **Format de la tracklist** — La tracklist doit être au format HTML tel que généré par Internet Archive. Un format de description personnalisé nécessitera d'adapter la classe `TracklistParser`.

---

## Dépannage

<details>
<summary><code>FileNotFoundError: [Errno 2] No such file or directory: 'ffmpeg'</code></summary>

ffmpeg n'est pas installé ou n'est pas dans le PATH.

```bash
# Vérification
ffmpeg -version
```

→ Installez ffmpeg en suivant les instructions de la section [Prérequis système](#prérequis-système).

</details>

<details>
<summary><code>ERREUR : pydub n'est pas installé</code></summary>

L'environnement virtuel n'est pas activé, ou pydub n'a pas été installé.

```bash
source .venv/bin/activate   # activer le venv
pip install pydub            # installer pydub
```

</details>

<details>
<summary><code>ERREUR : aucune piste trouvée dans les métadonnées</code></summary>

Le champ `<description>` du XML ne contient pas de tableau HTML au format attendu.

→ Vérifiez que la description contient bien un `<table class="... table_lyrics ...">` avec les durées au format `MM:SS` dans la troisième colonne.

</details>

<details>
<summary>Les fichiers générés n'ont pas de pochette</summary>

→ Vérifiez que le chemin passé à `--cover` est correct et que le fichier existe bien (JPG ou PNG uniquement).

</details>

<details>
<summary>Les noms de fichiers contiennent des underscores inattendus</summary>

Les caractères `< > : " / \ | ? *` sont interdits dans les noms de fichiers sur la plupart des systèmes d'exploitation. Ils sont remplacés automatiquement par `_`. C'est un comportement normal.

</details>

<details>
<summary>Performances lentes</summary>

Le chargement et l'export audio dépendent de ffmpeg et de la taille du fichier source. Un album de 50–60 Mo peut prendre de 30 secondes à quelques minutes selon la machine.

</details>

---

## Dépendances

| Bibliothèque | Version minimale | Lien |
|---|---|---|
| `pydub` | 0.25.0+ | [github.com/jiaaro/pydub](https://github.com/jiaaro/pydub) |
| `mutagen` | 1.45.0+ | [mutagen.readthedocs.io](https://mutagen.readthedocs.io) |
| `ffmpeg` | 4.0+ (externe) | [ffmpeg.org](https://ffmpeg.org) |

---

*Généré avec l'assistance de [Claude](https://claude.ai) (Anthropic) — Libre d'utilisation pour usage personnel.*
