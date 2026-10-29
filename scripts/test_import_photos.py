from pathlib import Path

import pytest
from PIL import Image

import import_photos as importer

GPS_IFD = 0x8825
ORIENTATION = 0x0112
ROTATED_90_CW = 6
GPS_LATITUDE_REF = 1
GPS_LATITUDE = 2


def make_jpeg(path: Path, taken_at: str, size=(2400, 1800), orientation=1) -> None:
    exif = Image.Exif()
    exif[ORIENTATION] = orientation
    exif.get_ifd(importer.EXIF_IFD)[importer.EXIF_DATETIME_ORIGINAL] = taken_at
    exif.get_ifd(GPS_IFD).update({GPS_LATITUDE_REF: "N", GPS_LATITUDE: (43.0, 39.0, 30.0)})
    Image.new("RGB", size, (173, 74, 43)).save(path, "JPEG", exif=exif, quality=90)


@pytest.fixture
def workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    source = tmp_path / "source" / "Chantier 03 - Muret en pierre"
    source.mkdir(parents=True)
    make_jpeg(source / "b.JPG", "2025:05:02 10:00:00")
    make_jpeg(source / "a.JPG", "2025:05:01 09:00:00", orientation=ROTATED_90_CW)
    repo = tmp_path / "repo"
    (repo / "_chantiers").mkdir(parents=True)
    return source.parent, source, repo


def run_import(source_root: Path, repo: Path) -> None:
    for folder in importer.source_folders(source_root, None):
        importer.import_folder(folder, repo)


def output_dir(repo: Path) -> Path:
    return repo / "assets" / "chantiers" / "chantier-03"


def test_outputs_carry_no_exif_gps_or_xmp(workspace):
    source_root, _, repo = workspace
    run_import(source_root, repo)
    outputs = sorted(output_dir(repo).glob("*.webp"))
    assert len(outputs) == 6
    for path in outputs:
        with Image.open(path) as image:
            assert not image.getexif()
            assert not {"exif", "xmp", "icc_profile"} & set(image.info)
        assert b"Exif" not in path.read_bytes()


def test_detects_metadata_left_in_output(tmp_path):
    leaky = tmp_path / "leaky.webp"
    exif = Image.Exif()
    exif.get_ifd(GPS_IFD)[GPS_LATITUDE_REF] = "N"
    Image.new("RGB", (10, 10)).save(leaky, "WEBP", exif=exif)
    with pytest.raises(importer.PhotoImportError):
        importer.assert_no_metadata(leaky)


def test_names_follow_capture_order_and_sizes_are_bounded(workspace):
    source_root, _, repo = workspace
    run_import(source_root, repo)
    names = sorted(path.name for path in output_dir(repo).glob("*.webp"))
    assert names == [
        "chantier-03-01-medium.webp", "chantier-03-01-thumb.webp", "chantier-03-01.webp",
        "chantier-03-02-medium.webp", "chantier-03-02-thumb.webp", "chantier-03-02.webp",
    ]
    with Image.open(output_dir(repo) / "chantier-03-01.webp") as first:
        assert first.size == (1200, 1600), "orientation applied before stripping EXIF"
    with Image.open(output_dir(repo) / "chantier-03-02-medium.webp") as medium:
        assert max(medium.size) == importer.MEDIUM_SIZE
    with Image.open(output_dir(repo) / "chantier-03-02-thumb.webp") as thumb:
        assert max(thumb.size) == importer.THUMB_SIZE


def test_creates_markdown_with_defaults(workspace):
    source_root, _, repo = workspace
    run_import(source_root, repo)
    markdown = repo / "_chantiers" / "chantier-03-muret-en-pierre.md"
    front, body = importer.read_markdown(markdown)
    assert front["title"] == "Muret en pierre"
    assert front["type"] == "clotures"
    assert str(front["date"]) == "2025-05-02"
    assert front["cover"] == "chantier-03-02"
    assert [photo["file"] for photo in front["photos"]] == ["chantier-03-01", "chantier-03-02"]
    assert body == importer.PLACEHOLDER_BODY


def test_rerun_keeps_written_text_and_alts(workspace):
    source_root, source, repo = workspace
    run_import(source_root, repo)
    markdown = repo / "_chantiers" / "chantier-03-muret-en-pierre.md"
    front, _ = importer.read_markdown(markdown)
    front.update(title="Muret de clôture", commune="Grasse", type="clotures", cover="chantier-03-01")
    front["photos"][0]["alt"] = "Fondation du muret"
    importer.write_markdown(markdown, front, "Mon texte.\n")
    make_jpeg(source / "c.JPG", "2025:05:03 08:00:00")

    run_import(source_root, repo)

    merged, body = importer.read_markdown(markdown)
    assert body == "Mon texte.\n"
    assert (merged["title"], merged["commune"], merged["cover"]) == ("Muret de clôture", "Grasse", "chantier-03-01")
    assert merged["photos"][0]["alt"] == "Fondation du muret"
    assert len(merged["photos"]) == 3


def test_renamed_source_folder_reuses_existing_markdown(workspace):
    source_root, source, repo = workspace
    run_import(source_root, repo)
    source.rename(source_root / "Chantier 03 - Muret Grasse")
    run_import(source_root, repo)
    assert [path.name for path in (repo / "_chantiers").glob("*.md")] == ["chantier-03-muret-en-pierre.md"]


def test_removes_outputs_of_deleted_photos(workspace):
    source_root, source, repo = workspace
    run_import(source_root, repo)
    (source / "b.JPG").unlink()
    run_import(source_root, repo)
    assert sorted(path.name for path in output_dir(repo).glob("*.webp")) == [
        "chantier-03-01-medium.webp", "chantier-03-01-thumb.webp", "chantier-03-01.webp",
    ]


def test_unsupported_files_are_reported_not_imported(workspace, capsys):
    source_root, source, repo = workspace
    (source / "notes.txt").write_text("adresse du client")
    run_import(source_root, repo)
    assert "skipped (unsupported format): notes.txt" in capsys.readouterr().err


def test_ignores_folders_not_named_chantier(tmp_path):
    (tmp_path / "Divers").mkdir()
    with pytest.raises(importer.PhotoImportError):
        importer.source_folders(tmp_path, None)


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Terrasse sur dalle vue mer", "terrasses"),
        ("Rénovation maison façade salle de bain cuisine", "renovation"),
        ("Mur de clôture et portail", "clotures"),
        ("Extension garage", "construction"),
    ],
)
def test_guess_type(description, expected):
    assert importer.guess_type(description) == expected


def test_export_dates_equal_to_today_are_not_used(workspace):
    source_root, source, repo = workspace
    today = importer.date.today().strftime("%Y:%m:%d")
    for path in source.glob("*.JPG"):
        make_jpeg(path, f"{today} 12:00:00")
    run_import(source_root, repo)
    front, _ = importer.read_markdown(repo / "_chantiers" / "chantier-03-muret-en-pierre.md")
    assert "date" not in front
    assert front["number"] == 3


def test_rerun_keeps_extra_assets_and_front_matter(workspace):
    source_root, _, repo = workspace
    run_import(source_root, repo)
    video = output_dir(repo) / "chantier-03-video.mp4"
    poster = output_dir(repo) / "chantier-03-video-poster.webp"
    video.write_bytes(b"video")
    Image.new("RGB", (10, 10)).save(poster, "WEBP")
    markdown = repo / "_chantiers" / "chantier-03-muret-en-pierre.md"
    front, body = importer.read_markdown(markdown)
    front["video"] = {"file": "chantier-03-video", "caption": "Le muret fini"}
    importer.write_markdown(markdown, front, body)

    run_import(source_root, repo)

    assert video.exists() and poster.exists()
    assert importer.read_markdown(markdown)[0]["video"]["caption"] == "Le muret fini"
