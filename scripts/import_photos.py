#!/usr/bin/env python3
"""Import job-site photos into the Jekyll site.

For each source folder named "Chantier NN - Description":
  - re-encode every photo as WebP (display, medium, thumbnail) from raw pixels only,
    so no EXIF / GPS / XMP metadata can reach the repository;
  - name outputs chantier-NN-01.webp, chantier-NN-01-medium.webp, chantier-NN-01-thumb.webp, ...;
  - create or update _chantiers/chantier-NN-*.md without overwriting text.

Originals are never copied into the repository.
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml
from PIL import Image, ImageCms, ImageOps

DISPLAY_SIZE = 1600
MEDIUM_SIZE = 800
THUMB_SIZE = 600
WEBP_QUALITY = 80
REPO_SIZE_LIMIT_BYTES = 500 * 1024 * 1024
OUTPUT_SUFFIXES = ("", "-medium", "-thumb")
SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
EXIF_DATETIME_ORIGINAL = 0x9003
EXIF_IFD = 0x8769
FOLDER_PATTERN = re.compile(r"^Chantier\s+(\d+)\s*-\s*(.+)$", re.IGNORECASE)
FRONT_MATTER_PATTERN = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)

TYPE_KEYWORDS = [
    ("clotures", ("clôture", "cloture", "muret", "portail", "soutènement")),
    ("terrasses", ("terrasse", "piscine", "plage", "dallage")),
    ("renovation", ("rénovation", "renovation", "salle de bain", "cuisine", "façade", "aménagement")),
]
DEFAULT_TYPE = "construction"
PLACEHOLDER_BODY = "Texte à écrire : ce qui a été fait, avec quels matériaux, en combien de temps.\n"

SRGB_PROFILE = ImageCms.createProfile("sRGB")


class PhotoImportError(Exception):
    """Raised when a job-site folder cannot be imported safely."""


@dataclass(frozen=True)
class SourceFolder:
    path: Path
    number: str
    description: str

    @property
    def key(self) -> str:
        return f"chantier-{self.number}"


@dataclass(frozen=True)
class ImportedPhoto:
    name: str
    width: int
    height: int
    thumb_width: int
    thumb_height: int
    taken_on: date | None


@dataclass(frozen=True)
class SourcePhoto:
    path: Path
    taken_at: datetime | None

    @property
    def sort_key(self) -> tuple[datetime, str]:
        return (self.taken_at or datetime.max, self.path.name)


def parse_folder(path: Path) -> SourceFolder | None:
    match = FOLDER_PATTERN.match(path.name)
    if not match:
        return None
    return SourceFolder(path, f"{int(match.group(1)):02d}", match.group(2).strip())


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def guess_type(description: str) -> str:
    lowered = description.lower()
    for job_type, keywords in TYPE_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return job_type
    return DEFAULT_TYPE


def capture_datetime(image: Image.Image) -> datetime | None:
    raw = image.getexif().get_ifd(EXIF_IFD).get(EXIF_DATETIME_ORIGINAL)
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw).strip("\x00 "), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        print(f"  warning: unreadable capture date {raw!r}", file=sys.stderr)
        return None


def list_photos(folder: Path) -> list[Path]:
    photos, skipped = [], []
    for path in sorted(folder.iterdir()):
        if path.name.startswith("."):
            continue
        (photos if path.suffix.lower() in SUPPORTED_SUFFIXES else skipped).append(path)
    for path in skipped:
        print(f"  skipped (unsupported format): {path.name}", file=sys.stderr)
    return photos


def read_source_photos(folder: Path) -> list[SourcePhoto]:
    sources = []
    for path in list_photos(folder):
        with Image.open(path) as image:
            sources.append(SourcePhoto(path, capture_datetime(image)))
    return sorted(sources, key=lambda source: source.sort_key)


def to_srgb(image: Image.Image) -> Image.Image:
    icc_profile = image.info.get("icc_profile")
    if not icc_profile:
        return image.convert("RGB")
    source_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc_profile))
    return ImageCms.profileToProfile(image, source_profile, SRGB_PROFILE, outputMode="RGB")


def pixels_only(path: Path) -> Image.Image:
    """Return a fresh image carrying nothing but upright sRGB pixels."""
    with Image.open(path) as source:
        upright = ImageOps.exif_transpose(source)
        try:
            rgb = to_srgb(upright)
        except (ImageCms.PyCMSError, OSError) as error:
            print(f"  warning: {path.name}: colour profile ignored ({error})", file=sys.stderr)
            rgb = upright.convert("RGB")
    return Image.frombytes("RGB", rgb.size, rgb.tobytes())


def webp_chunk_ids(data: bytes) -> set[str]:
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise PhotoImportError("output is not a WebP file")
    chunk_ids, offset = set(), 12
    while offset + 8 <= len(data):
        chunk_ids.add(data[offset:offset + 4].decode("latin-1"))
        size = int.from_bytes(data[offset + 4:offset + 8], "little")
        offset += 8 + size + (size % 2)
    return chunk_ids


def assert_no_metadata(path: Path) -> None:
    leaked = webp_chunk_ids(path.read_bytes()) & {"EXIF", "XMP ", "ICCP"}
    if leaked:
        raise PhotoImportError(f"{path.name} still carries metadata chunks: {sorted(leaked)}")


def save_webp(image: Image.Image, destination: Path, max_size: int) -> tuple[int, int]:
    resized = image.copy()
    resized.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    resized.save(destination, "WEBP", quality=WEBP_QUALITY, method=6)
    assert_no_metadata(destination)
    return resized.size


def import_photo(source: SourcePhoto, output_dir: Path, name: str) -> ImportedPhoto:
    image = pixels_only(source.path)
    width, height = save_webp(image, output_dir / f"{name}.webp", DISPLAY_SIZE)
    save_webp(image, output_dir / f"{name}-medium.webp", MEDIUM_SIZE)
    thumb_width, thumb_height = save_webp(image, output_dir / f"{name}-thumb.webp", THUMB_SIZE)
    taken_on = source.taken_at.date() if source.taken_at else None
    return ImportedPhoto(name, width, height, thumb_width, thumb_height, taken_on)


def remove_stale_outputs(output_dir: Path, folder: SourceFolder, kept: set[str]) -> None:
    pattern = re.compile(rf"^{folder.key}-\d+(-medium|-thumb)?\.webp$")
    for path in sorted(output_dir.glob("*.webp")):
        if pattern.match(path.name) and path.name not in kept:
            print(f"  removed stale output: {path.name}")
            path.unlink()


def import_folder_photos(folder: SourceFolder, output_dir: Path) -> list[ImportedPhoto]:
    sources = read_source_photos(folder.path)
    if not sources:
        raise PhotoImportError(f"no supported photo in {folder.path.name}")
    output_dir.mkdir(parents=True, exist_ok=True)
    imported = [
        import_photo(source, output_dir, f"{folder.key}-{index:02d}")
        for index, source in enumerate(sources, start=1)
    ]
    kept = {f"{photo.name}{suffix}.webp" for photo in imported for suffix in OUTPUT_SUFFIXES}
    remove_stale_outputs(output_dir, folder, kept)
    return imported


def find_markdown(chantiers_dir: Path, folder: SourceFolder) -> Path:
    matches = sorted(chantiers_dir.glob(f"{folder.key}.md")) + sorted(chantiers_dir.glob(f"{folder.key}-*.md"))
    if len(matches) > 1:
        raise PhotoImportError(f"several Markdown files for {folder.key}: {[m.name for m in matches]}")
    if matches:
        return matches[0]
    return chantiers_dir / f"{folder.key}-{slugify(folder.description)}.md"


def read_markdown(path: Path) -> tuple[dict, str]:
    if not path.exists():
        return {}, PLACEHOLDER_BODY
    match = FRONT_MATTER_PATTERN.match(path.read_text(encoding="utf-8"))
    if not match:
        raise PhotoImportError(f"{path.name} has no YAML front matter; fix it by hand first")
    return yaml.safe_load(match.group(1)) or {}, match.group(2)


def photo_entries(photos: list[ImportedPhoto], title: str, existing: list[dict]) -> list[dict]:
    known_alts = {entry.get("file"): entry.get("alt") for entry in existing or [] if isinstance(entry, dict)}
    return [
        {
            "file": photo.name,
            "width": photo.width,
            "height": photo.height,
            "thumb_width": photo.thumb_width,
            "thumb_height": photo.thumb_height,
            "alt": known_alts.get(photo.name) or f"{title}, photo {index} sur {len(photos)}",
        }
        for index, photo in enumerate(photos, start=1)
    ]


def job_date(photos: list[ImportedPhoto], today: date) -> date | None:
    """Latest capture date, unless every date is today: that is an export date, not a shot date."""
    dates = {photo.taken_on for photo in photos if photo.taken_on}
    if not dates:
        return None
    if dates == {today}:
        print("  warning: capture dates are today's (re-exported photos); date left for you to fill", file=sys.stderr)
        return None
    return max(dates)


def default_front_matter(folder: SourceFolder, photos: list[ImportedPhoto]) -> dict:
    front_matter = {
        "title": folder.description,
        "number": int(folder.number),
        "commune": "",
        "type": guess_type(folder.description),
        "description": "",
        "cover": photos[-1].name,
        "before": "",
        "after": "",
    }
    taken_on = job_date(photos, date.today())
    if taken_on:
        front_matter["date"] = taken_on
    return front_matter


def merge_front_matter(existing: dict, folder: SourceFolder, photos: list[ImportedPhoto]) -> dict:
    merged = default_front_matter(folder, photos)
    merged.update({key: value for key, value in existing.items() if key != "photos"})
    merged["folder"] = folder.key
    merged["number"] = int(folder.number)
    merged["photos"] = photo_entries(photos, merged["title"], existing.get("photos"))
    names = {photo.name for photo in photos}
    for field in ("cover", "before", "after"):
        if merged.get(field) and merged[field] not in names:
            print(f"  warning: {field} '{merged[field]}' no longer matches a photo", file=sys.stderr)
    return merged


def write_markdown(path: Path, front_matter: dict, body: str) -> None:
    rendered_front = yaml.safe_dump(front_matter, allow_unicode=True, sort_keys=False, width=1000)
    content = f"---\n{rendered_front}---\n{body}"
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.write_text(content, encoding="utf-8")
    print(f"  wrote {path.name}")


def import_folder(folder: SourceFolder, repo: Path) -> None:
    print(f"{folder.path.name} -> {folder.key}")
    photos = import_folder_photos(folder, repo / "assets" / "chantiers" / folder.key)
    markdown_path = find_markdown(repo / "_chantiers", folder)
    existing, body = read_markdown(markdown_path)
    write_markdown(markdown_path, merge_front_matter(existing, folder, photos), body)
    print(f"  {len(photos)} photos")


def directory_size(path: Path) -> int:
    return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())


def source_folders(source_root: Path, only: str | None) -> list[SourceFolder]:
    folders = [parse_folder(path) for path in sorted(source_root.iterdir()) if path.is_dir()]
    selected = [folder for folder in folders if folder and (only is None or folder.number == f"{int(only):02d}")]
    if not selected:
        raise PhotoImportError(f"no 'Chantier NN - Description' folder found in {source_root}")
    return selected


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, default=Path.home() / "Documents" / "photos papa" / "_Tri par chantier")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--only", help="import a single chantier number, e.g. 7")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        for folder in source_folders(args.source, args.only):
            import_folder(folder, args.repo)
        total = directory_size(args.repo / "assets")
        print(f"assets: {total / 1024 / 1024:.1f} MB")
        if total > REPO_SIZE_LIMIT_BYTES:
            raise PhotoImportError("assets exceed the 500 MB repository budget")
    except PhotoImportError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
