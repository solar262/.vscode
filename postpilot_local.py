"""PostPilot Local command-line app.

This module keeps the local posting queue simple: videos live in the Inbox
folder and each queued video has a small JSON manifest beside it. Imported
posts are also recorded in app/data/imported_posts.json for audit/history.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

DOWNLOADS_DIR = Path(os.environ.get("POSTPILOT_DOWNLOADS_DIR", r"C:\Users\qwerty\Downloads"))
DATA_DIR = Path("app/data")
INBOX_DIR = DATA_DIR / "inbox"
IMPORTED_POSTS_PATH = DATA_DIR / "imported_posts.json"
LATEST_DOWNLOAD_LIMIT = 10


@dataclass(frozen=True)
class BrandDefaults:
    key: str
    display_name: str
    filename_prefix: str
    caption: str
    website: str


BRANDS: dict[str, BrandDefaults] = {
    "1": BrandDefaults(
        key="hairhub",
        display_name="HairHub",
        filename_prefix="hairhub_external",
        caption="Fresh HairHub inspiration is here. Book your next look today.",
        website="https://hairhub.example.com",
    ),
    "2": BrandDefaults(
        key="beans",
        display_name="Beans Perfeto",
        filename_prefix="beans_external",
        caption="Beans Perfeto brings rich coffee moments to your day.",
        website="https://beansperfeto.example.com",
    ),
}


@dataclass(frozen=True)
class DownloadCandidate:
    path: Path
    size_bytes: int
    modified_at: datetime


def ensure_app_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    INBOX_DIR.mkdir(parents=True, exist_ok=True)


def human_size(size_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    size = float(size_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size_bytes} B"


def scan_recent_downloads(downloads_dir: Path | None = None, limit: int = LATEST_DOWNLOAD_LIMIT) -> list[DownloadCandidate]:
    """Return the newest MP4 downloads, newest first."""

    downloads_dir = downloads_dir or DOWNLOADS_DIR
    if not downloads_dir.exists():
        return []

    candidates: list[DownloadCandidate] = []
    for path in downloads_dir.iterdir():
        if not path.is_file() or path.suffix.lower() != ".mp4":
            continue
        stat = path.stat()
        candidates.append(
            DownloadCandidate(
                path=path,
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime),
            )
        )

    candidates.sort(key=lambda candidate: candidate.modified_at, reverse=True)
    return candidates[:limit]


def format_download_candidate(number: int, candidate: DownloadCandidate) -> str:
    modified = candidate.modified_at.strftime("%Y-%m-%d %H:%M:%S")
    return f"{number}. {candidate.path.name} | {human_size(candidate.size_bytes)} | {modified}"


def parse_selection(selection: str, candidate_count: int) -> list[int]:
    """Parse a 1-based selection list or `all` into zero-based indexes."""

    normalized = selection.strip().lower()
    if not normalized:
        return []
    if normalized == "all":
        return list(range(candidate_count))

    indexes: list[int] = []
    for token in re.split(r"[\s,]+", normalized):
        if not token:
            continue
        if not token.isdigit():
            raise ValueError(f"Invalid selection: {token}")
        number = int(token)
        if number < 1 or number > candidate_count:
            raise ValueError(f"Selection out of range: {number}")
        index = number - 1
        if index not in indexes:
            indexes.append(index)
    return indexes


def next_safe_queue_name(brand: BrandDefaults, inbox_dir: Path = INBOX_DIR) -> str:
    inbox_dir.mkdir(parents=True, exist_ok=True)
    pattern = re.compile(rf"^{re.escape(brand.filename_prefix)}_(\d{{3}})\.mp4$", re.IGNORECASE)
    used_numbers = []
    for path in inbox_dir.glob(f"{brand.filename_prefix}_*.mp4"):
        match = pattern.match(path.name)
        if match:
            used_numbers.append(int(match.group(1)))

    next_number = max(used_numbers, default=0) + 1
    while True:
        name = f"{brand.filename_prefix}_{next_number:03d}.mp4"
        if not (inbox_dir / name).exists():
            return name
        next_number += 1


def read_json_list(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return data if isinstance(data, list) else []


def write_json_list(path: Path, rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(list(rows), file, indent=2)


def create_manifest(video_path: Path, brand: BrandDefaults, source_path: Path) -> dict[str, object]:
    manifest = {
        "video": str(video_path),
        "filename": video_path.name,
        "brand": brand.display_name,
        "brand_key": brand.key,
        "caption": brand.caption,
        "website": brand.website,
        "source": str(source_path),
        "status": "queued",
        "imported_at": datetime.now().isoformat(timespec="seconds"),
    }
    with video_path.with_suffix(".json").open("w", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2)
    return manifest


def record_import(manifest: dict[str, object], imported_posts_path: Path = IMPORTED_POSTS_PATH) -> None:
    rows = read_json_list(imported_posts_path)
    rows.append(manifest)
    write_json_list(imported_posts_path, rows)


def import_video_to_queue(
    source_path: Path,
    brand: BrandDefaults,
    inbox_dir: Path | None = None,
    imported_posts_path: Path | None = None,
) -> dict[str, object]:
    """Copy a downloaded video into Inbox with a safe brand filename and manifest."""

    inbox_dir = inbox_dir or INBOX_DIR
    imported_posts_path = imported_posts_path or IMPORTED_POSTS_PATH
    inbox_dir.mkdir(parents=True, exist_ok=True)
    imported_posts_path.parent.mkdir(parents=True, exist_ok=True)
    safe_name = next_safe_queue_name(brand, inbox_dir)
    destination = inbox_dir / safe_name
    shutil.copy2(source_path, destination)
    manifest = create_manifest(destination, brand, source_path)
    record_import(manifest, imported_posts_path)
    return manifest


def load_queue(inbox_dir: Path | None = None) -> list[dict[str, object]]:
    inbox_dir = inbox_dir or INBOX_DIR
    queue: list[dict[str, object]] = []
    if not inbox_dir.exists():
        return queue

    for video_path in sorted(inbox_dir.glob("*.mp4")):
        manifest_path = video_path.with_suffix(".json")
        if manifest_path.exists():
            with manifest_path.open("r", encoding="utf-8") as file:
                manifest = json.load(file)
        else:
            manifest = {
                "video": str(video_path),
                "filename": video_path.name,
                "brand": "Unknown",
                "caption": "",
                "website": "",
                "status": "queued",
            }
        if manifest.get("status", "queued") == "queued":
            queue.append(manifest)
    return queue


def open_queue(print_fn: Callable[[str], None] = print) -> list[dict[str, object]]:
    queue = load_queue()
    if not queue:
        print_fn("Queue is empty.")
        return queue

    print_fn("Inbox queue:")
    for number, manifest in enumerate(queue, start=1):
        print_fn(
            f"{number}. {manifest.get('filename')} | {manifest.get('brand')} | "
            f"caption: {manifest.get('caption')} | website: {manifest.get('website')}"
        )
    return queue


def mark_uploaded(manifest: dict[str, object]) -> None:
    video_path = Path(str(manifest["video"]))
    manifest["status"] = "uploaded"
    manifest["uploaded_at"] = datetime.now().isoformat(timespec="seconds")
    with video_path.with_suffix(".json").open("w", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2)

    rows = read_json_list(IMPORTED_POSTS_PATH)
    for row in rows:
        if row.get("video") == manifest.get("video"):
            row.update(manifest)
    write_json_list(IMPORTED_POSTS_PATH, rows)


def upload_next_post(print_fn: Callable[[str], None] = print) -> dict[str, object] | None:
    queue = load_queue()
    if not queue:
        print_fn("No queued posts to upload.")
        return None

    manifest = queue[0]
    print_fn(f"Uploading next post: {manifest.get('filename')}")
    print_fn(f"Caption: {manifest.get('caption')}")
    print_fn(f"Website: {manifest.get('website')}")
    mark_uploaded(manifest)
    print_fn("Upload prepared with the correct caption and website.")
    return manifest


def prompt_brand(input_fn: Callable[[str], str] = input, print_fn: Callable[[str], None] = print) -> BrandDefaults | None:
    print_fn("Which brand?")
    print_fn("1 = HairHub")
    print_fn("2 = Beans Perfeto")
    print_fn("3 = Skip")
    choice = input_fn("Brand: ").strip()
    if choice == "3":
        return None
    return BRANDS.get(choice)


def import_recent_downloads(
    downloads_dir: Path | None = None,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> int:
    downloads_dir = downloads_dir or DOWNLOADS_DIR
    candidates = scan_recent_downloads(downloads_dir)
    if not candidates:
        print_fn(f"No recent MP4 files found in {downloads_dir}.")
        return 0

    print_fn("Recent MP4 downloads:")
    for number, candidate in enumerate(candidates, start=1):
        print_fn(format_download_candidate(number, candidate))

    try:
        selected_indexes = parse_selection(input_fn("Select files by number, or type all: "), len(candidates))
    except ValueError as exc:
        print_fn(str(exc))
        return 0

    imported_count = 0
    for index in selected_indexes:
        candidate = candidates[index]
        print_fn(f"Selected: {candidate.path.name}")
        brand = prompt_brand(input_fn, print_fn)
        if not brand:
            print_fn("Skipped.")
            continue
        import_video_to_queue(candidate.path, brand)
        imported_count += 1

    print_fn(f"Imported {imported_count} videos into queue.")
    return imported_count


def open_downloads_folder(downloads_dir: Path = DOWNLOADS_DIR, print_fn: Callable[[str], None] = print) -> None:
    downloads_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(downloads_dir))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(downloads_dir)])
    else:
        subprocess.Popen(["xdg-open", str(downloads_dir)])
    print_fn(f"Opened Downloads folder: {downloads_dir}")


def print_menu(print_fn: Callable[[str], None] = print) -> None:
    print_fn("\nPostPilot Local")
    print_fn("2 = Open queue")
    print_fn("3 = Upload next post")
    print_fn("16 = Import recent downloads")
    print_fn("17 = Open Downloads folder")
    print_fn("0 = Exit")


def main() -> None:
    ensure_app_dirs()
    while True:
        print_menu()
        choice = input("Choose option: ").strip()
        if choice == "2":
            open_queue()
        elif choice == "3":
            upload_next_post()
        elif choice == "16":
            import_recent_downloads()
        elif choice == "17":
            open_downloads_folder()
        elif choice == "0":
            break
        else:
            print("Unknown option.")


if __name__ == "__main__":
    main()
