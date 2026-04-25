#!/usr/bin/env python3
"""
split_album.py — Découpe un fichier MP3 album en pistes individuelles,
en lisant les métadonnées depuis un fichier XML
et/ou SQLite, puis écrit les balises ID3 + image de couverture.

Dépendances :
    pip install pydub mutagen

Pydub utilise ffmpeg (ou avconv) pour le décodage/encodage.
Installe ffmpeg : https://ffmpeg.org/download.html

Usage :
    python split_album.py \
        --mp3     "northern-lights-echoes-of-the-storm.mp3" \
        --xml     "northern-lights-echoes-of-the-storm_meta.xml" \
        --sqlite  "northern-lights-echoes-of-the-storm_meta.sqlite" \
        --cover   "cover.jpg" \
        --outdir  "~/Musique"

Structure de sortie (exemple) :
    ~/Musique/
    └── <Artiste>/                        ← nom du groupe ou de l'artiste
        └── <Album (Année)>/              ← titre de l'album + année
            ├── 01 - <Titre piste 1>.mp3
            ├── 02 - <Titre piste 2>.mp3
            └── ...
"""

import argparse
import os
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

# ── Tentative d'import des dépendances optionnelles ──────────────────────────
try:
    from pydub import AudioSegment
except ImportError:
    AudioSegment = None  # Le découpage audio sera impossible sans pydub

try:
    from mutagen.id3 import (
        ID3, ID3NoHeaderError,
        TIT2, TPE1, TALB, TDRC, TRCK, TCON, TPUB,
        APIC, COMM,
    )
    from mutagen.mp3 import MP3
except ImportError:
    print("ERREUR : mutagen est requis.  pip install mutagen", file=sys.stderr)
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
#  Parser HTML minimal pour extraire la tracklist depuis la description IA
# ═══════════════════════════════════════════════════════════════════════════════
class TracklistParser(HTMLParser):
    """Extrait les paires (numéro, titre, durée) depuis le HTML de la tracklist."""

    def __init__(self):
        super().__init__()
        self.tracks: list[dict] = []
        self._in_table = False
        self._in_td = False
        self._current_row: list[str] = []
        self._cell_text = ""
        self._td_count = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "table" and "table_lyrics" in attrs_dict.get("class", ""):
            self._in_table = True
        if self._in_table:
            if tag == "tr":
                self._current_row = []
                self._td_count = 0
            if tag == "td":
                self._in_td = True
                self._cell_text = ""
                self._td_count += 1

    def handle_endtag(self, tag):
        if self._in_table and tag == "td":
            self._in_td = False
            self._current_row.append(self._cell_text.strip())
        if self._in_table and tag == "tr" and len(self._current_row) >= 3:
            # Cellule 0 : "1." ou "2." …  Cellule 1 : titre  Cellule 2 : "04:21"
            num_raw = self._current_row[0].strip().rstrip(".")
            title   = self._current_row[1].strip()
            dur_raw = self._current_row[2].strip()
            num_clean = re.sub(r"\D", "", num_raw)
            if num_clean and title and re.match(r"\d+:\d{2}", dur_raw):
                self.tracks.append({
                    "number":   int(num_clean),
                    "title":    title,
                    "duration": dur_raw,
                })

    def handle_data(self, data):
        if self._in_td:
            self._cell_text += data

    def handle_endtag(self, tag):  # noqa: F811  (redéfinition volontaire)
        if self._in_table and tag == "td":
            self._in_td = False
            self._current_row.append(self._cell_text.strip())
        if self._in_table and tag == "tr":
            row = self._current_row
            if len(row) >= 3:
                num_raw  = re.sub(r"\D", "", row[0])
                title    = row[1].strip()
                dur_raw  = row[2].strip()
                if num_raw and title and re.match(r"\d+:\d{2}", dur_raw):
                    self.tracks.append({
                        "number":   int(num_raw),
                        "title":    title,
                        "duration": dur_raw,
                    })
            self._current_row = []
        if tag == "table":
            self._in_table = False


# ═══════════════════════════════════════════════════════════════════════════════
#  Lecture des métadonnées
# ═══════════════════════════════════════════════════════════════════════════════
def parse_xml(xml_path: str) -> dict:
    """Retourne les métadonnées album et la tracklist depuis le XML Internet Archive."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    def get(tag, default=""):
        el = root.find(tag)
        return el.text.strip() if el is not None and el.text else default

    def get_all(tag):
        return [el.text.strip() for el in root.findall(tag) if el.text]

    meta = {
        "title":      get("title"),
        "creator":    get("creator"),
        "date":       get("date"),          # "1998-10-05"
        "year":       get("date", "")[:4],  # "1998"
        "label":      get("label"),
        "genres":     get_all("genre"),
        "collection": get("collection"),
        "language":   get("language"),
        "runtime":    get("runtime"),
        "tracks":     [],
    }

    # Tracklist depuis la description HTML
    description = get("description")
    if description:
        parser = TracklistParser()
        parser.feed(description)
        meta["tracks"] = sorted(parser.tracks, key=lambda t: t["number"])

    return meta


def parse_sqlite(sqlite_path: str) -> dict:
    """Extrait les métadonnées supplémentaires depuis la base SQLite (optionnel)."""
    extra = {}
    try:
        conn = sqlite3.connect(sqlite_path)
        c = conn.cursor()
        # Les headers HTTP IA contiennent les métadonnées encodées
        c.execute("SELECT s3key, headers FROM s3api_per_key_metadata WHERE s3key LIKE '%.mp3'")
        row = c.fetchone()
        if row:
            headers_text = row[1] if isinstance(row[1], str) else row[1].decode("utf-8", errors="replace")
            # On peut raffiner ici si nécessaire ; pour l'instant on extrait le titre
            for line in headers_text.splitlines():
                if "x-archive-meta01-title" in line:
                    match = re.search(r"uri\((.+?)\)", line)
                    if match:
                        from urllib.parse import unquote
                        extra["title_from_sqlite"] = unquote(match.group(1))
        conn.close()
    except Exception as e:
        print(f"[WARN] SQLite ignoré : {e}", file=sys.stderr)
    return extra


# ═══════════════════════════════════════════════════════════════════════════════
#  Utilitaires
# ═══════════════════════════════════════════════════════════════════════════════
def duration_to_ms(duration_str: str) -> int:
    """Convertit 'MM:SS' en millisecondes."""
    parts = duration_str.split(":")
    if len(parts) == 2:
        return (int(parts[0]) * 60 + int(parts[1])) * 1000
    if len(parts) == 3:
        return (int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])) * 1000
    return 0


def sanitize_filename(name: str) -> str:
    """Supprime les caractères interdits dans les noms de fichiers/dossiers."""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip()


def build_output_path(base_dir: str, meta: dict) -> Path:
    """
    Construit le chemin de sortie :
      base_dir / <artiste ou collection> / <album (année)>
    """
    artist     = sanitize_filename(meta.get("creator") or "Artiste inconnu")
    album      = sanitize_filename(meta.get("title")   or "Album inconnu")
    year       = meta.get("year", "")
    collection = meta.get("collection", "")

    # Dossier racine : artiste, ou collection si l'artiste n'est pas renseigné
    root_name = artist if artist else sanitize_filename(collection) if collection else "Inconnu"
    album_dir = f"{album} ({year})" if year else album

    path = Path(base_dir) / root_name / album_dir
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_id3_tags(mp3_path: str, track: dict, meta: dict, cover_path: str | None):
    """Écrit les balises ID3v2 sur le fichier mp3_path."""
    try:
        tags = ID3(mp3_path)
    except ID3NoHeaderError:
        tags = ID3()

    tags.add(TIT2(encoding=3, text=track["title"]))
    tags.add(TPE1(encoding=3, text=meta.get("creator", "")))
    tags.add(TALB(encoding=3, text=meta.get("title", "")))
    tags.add(TDRC(encoding=3, text=meta.get("year", "")))
    tags.add(TRCK(encoding=3, text=f"{track['number']}/{len(meta['tracks'])}"))

    genres = meta.get("genres", [])
    if genres:
        tags.add(TCON(encoding=3, text="; ".join(genres)))

    label = meta.get("label", "")
    if label:
        tags.add(TPUB(encoding=3, text=label))

    if cover_path and os.path.isfile(cover_path):
        ext = os.path.splitext(cover_path)[1].lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
        mime = mime_map.get(ext, "image/jpeg")
        with open(cover_path, "rb") as fh:
            cover_data = fh.read()
        tags.add(APIC(
            encoding=3,
            mime=mime,
            type=3,      # Cover (front)
            desc="Cover",
            data=cover_data,
        ))

    tags.save(mp3_path, v2_version=3)


# ═══════════════════════════════════════════════════════════════════════════════
#  Découpage audio
# ═══════════════════════════════════════════════════════════════════════════════
def split_mp3(mp3_path: str, tracks: list[dict], output_dir: Path,
              meta: dict, cover_path: str | None):
    """Découpe le MP3 source en fichiers individuels et y écrit les tags."""

    if AudioSegment is None:
        print(
            "ERREUR : pydub n'est pas installé.  pip install pydub\n"
            "         Assurez-vous également d'avoir ffmpeg dans votre PATH.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"→ Chargement de {mp3_path} …")
    audio = AudioSegment.from_mp3(mp3_path)
    total_ms = len(audio)
    print(f"  Durée totale : {total_ms // 60000}:{(total_ms // 1000) % 60:02d}")

    # Calcul des points de découpe à partir des durées de la tracklist
    cut_points_ms: list[int] = [0]
    for track in tracks:
        cut_points_ms.append(cut_points_ms[-1] + duration_to_ms(track["duration"]))

    for i, track in enumerate(tracks):
        start = cut_points_ms[i]
        # Le dernier morceau s'étend jusqu'à la fin du fichier
        end = cut_points_ms[i + 1] if i + 1 < len(cut_points_ms) else total_ms

        segment = audio[start:end]
        safe_title = sanitize_filename(track["title"])
        filename   = f"{track['number']:02d} - {safe_title}.mp3"
        out_path   = output_dir / filename

        print(f"  [{track['number']:02d}/{len(tracks)}] {track['title']} "
              f"({track['duration']})  →  {out_path.name}")

        segment.export(str(out_path), format="mp3", bitrate="320k")
        write_id3_tags(str(out_path), track, meta, cover_path)

    print(f"\n✓ {len(tracks)} piste(s) exportée(s) dans : {output_dir}")


# ═══════════════════════════════════════════════════════════════════════════════
#  Point d'entrée
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="Découpe un fichier MP3 album en pistes individuelles avec balises ID3.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--mp3",    required=True, help="Fichier MP3 source (album complet)")
    parser.add_argument("--xml",    required=False, default=None,
                        help="Fichier XML de métadonnées")
    parser.add_argument("--sqlite", required=False, default=None,
                        help="Fichier SQLite de métadonnées")
    parser.add_argument("--cover",  required=False, default=None,
                        help="Image de couverture de l'album (JPG ou PNG)")
    parser.add_argument("--outdir", required=False, default=".",
                        help="Répertoire de sortie de base (défaut : répertoire courant)")
    args = parser.parse_args()

    # ── Validation des fichiers d'entrée ──
    if not os.path.isfile(args.mp3):
        print(f"ERREUR : fichier MP3 introuvable : {args.mp3}", file=sys.stderr)
        sys.exit(1)

    # ── Lecture des métadonnées ──
    meta: dict = {}
    if args.xml and os.path.isfile(args.xml):
        print(f"→ Lecture XML : {args.xml}")
        meta = parse_xml(args.xml)
    else:
        if args.xml:
            print(f"[WARN] XML introuvable : {args.xml}", file=sys.stderr)

    if args.sqlite and os.path.isfile(args.sqlite):
        print(f"→ Lecture SQLite : {args.sqlite}")
        extra = parse_sqlite(args.sqlite)
        # Si le XML n'a pas fourni de titre, on prend celui du SQLite
        if not meta.get("title") and extra.get("title_from_sqlite"):
            meta["title"] = extra["title_from_sqlite"]
    else:
        if args.sqlite:
            print(f"[WARN] SQLite introuvable : {args.sqlite}", file=sys.stderr)

    if not meta:
        print("ERREUR : aucun fichier de métadonnées valide fourni (--xml ou --sqlite).",
              file=sys.stderr)
        sys.exit(1)

    tracks = meta.get("tracks", [])
    if not tracks:
        print("ERREUR : aucune piste trouvée dans les métadonnées.", file=sys.stderr)
        sys.exit(1)

    print(f"\n── Album : {meta.get('title')} ({meta.get('year')}) ──")
    print(f"   Artiste : {meta.get('creator')}")
    print(f"   Label   : {meta.get('label')}")
    print(f"   Genre   : {', '.join(meta.get('genres', []))}")
    print(f"   Pistes  : {len(tracks)}\n")

    # ── Chemin de sortie ──
    output_dir = build_output_path(args.outdir, meta)
    print(f"→ Répertoire de sortie : {output_dir}\n")

    # ── Découpage ──
    split_mp3(args.mp3, tracks, output_dir, meta, args.cover)


if __name__ == "__main__":
    main()
