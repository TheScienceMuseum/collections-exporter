#!/usr/bin/env python3
"""Collections Exporter — extract data from the SMG Collections Online ES index."""

from __future__ import annotations

import argparse
import configparser
import csv
import json
import os
import sys
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import requests
from elasticsearch import Elasticsearch
from slugify import slugify


def load_config(config_path: str = ".config") -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    if not os.path.exists(config_path):
        print(f"Error: config file '{config_path}' not found. Copy .config.template to .config and fill in values.")
        sys.exit(1)
    config.read(config_path)
    return config


def create_es_client(node_url: str) -> Elasticsearch:
    """Create an Elasticsearch client, extracting auth from the URL if present."""
    parsed = urlparse(node_url)
    if parsed.username:
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path_prefix = parsed.path.rstrip("/")
        return Elasticsearch(
            f"{parsed.scheme}://{host}:{port}{path_prefix}",
            http_auth=(parsed.username, parsed.password),
        )
    return Elasticsearch(node_url)


def get_primary_value(field_list: Optional[list]) -> str:
    """Extract the primary value from a typed field array, falling back to the first entry."""
    if not field_list:
        return ""
    for item in field_list:
        if isinstance(item, dict) and item.get("primary"):
            return item.get("value", "")
    if isinstance(field_list[0], dict):
        return field_list[0].get("value", "")
    return str(field_list[0])


def get_creation_field(creation: Optional[dict], field: str) -> str:
    """Extract a creation sub-field from the catalogue/literal entry.

    Dates use source="catalogue" with a top-level .value.
    Maker/place use @entity="literal" with .name[0].value.
    """
    if not creation:
        return ""
    for entry in creation.get(field, []):
        if not isinstance(entry, dict):
            continue
        if entry.get("@entity") == "literal" or entry.get("source") == "catalogue":
            return entry.get("value", "") or (
                entry.get("name", [{}])[0].get("value", "") if entry.get("name") else ""
            )
    return ""


def get_materials(source: dict) -> str:
    """Extract materials as a semicolon-separated list."""
    materials = source.get("material", [])
    if not materials:
        return ""
    values = [m["value"] for m in materials if isinstance(m, dict) and m.get("value")]
    return "; ".join(values)


def get_measurements_display(source: dict) -> str:
    """Extract measurements display string."""
    measurements = source.get("measurements", {})
    if not measurements:
        return ""
    dimensions = measurements.get("dimensions", [])
    value = get_primary_value(dimensions)
    return value.lstrip(": ")


def get_object_name(source: dict) -> str:
    """Extract the primary object name from name array."""
    return get_primary_value(source.get("name", []))


def build_url(base_url: str, uid: str, title: str) -> str:
    """Build the public collection URL for an object."""
    slug = slugify(title) if title else ""
    return f"{base_url}/objects/{uid}/{slug}"


def build_query(categories: list, exclude_categories: list, before_year: Optional[int]) -> dict:
    """Build the ES query for Mimsy object records with given filters."""
    must = [
        {"term": {"@admin.source": "Mimsy XG"}},
        {"term": {"@datatype.base": "object"}},
    ]
    must_not = []

    if categories:
        must.append({"terms": {"category.name.keyword": categories}})

    if exclude_categories:
        must_not.append({"terms": {"category.name.keyword": exclude_categories}})

    if before_year is not None:
        must.append({"range": {"creation.date.to": {"lt": str(before_year)}}})

    query = {"bool": {"must": must}}
    if must_not:
        query["bool"]["must_not"] = must_not
    return query


SOURCE_FIELDS = [
    "@admin.uid",
    "@admin.added",
    "@admin.processed",
    "summary.title",
    "title",
    "description",
    "creation",
    "category",
    "identifier",
    "material",
    "measurements",
    "name",
]

IMAGE_SOURCE_FIELDS = SOURCE_FIELDS + ["multimedia"]

CSV_HEADERS = [
    "identifier",
    "uid",
    "created",
    "modified",
    "title",
    "object_name",
    "description",
    "date_made",
    "place_made",
    "maker",
    "category",
    "materials",
    "measurements",
    "url",
]

IMAGE_CSV_HEADERS = CSV_HEADERS + [
    "image_path",
    "image_licence",
    "image_copyright",
    "image_credit",
]


OPEN_LICENCES = [
    "CC BY-NC-SA 4.0",
    "CC-BY-NC-SA 4.0",
    "CC BY-NC-ND 4.0",
    "Open Government Licence v3.0",
]

EMPTY_IMAGE_FIELDS = {"image_path": "", "image_licence": "", "image_copyright": "", "image_credit": ""}


def get_image_fields(source: dict, media_path: str, open_licence_only: bool = True, download_images: bool = False) -> dict:
    """Extract first multimedia medium image path and legal fields."""
    multimedia = source.get("multimedia", [])
    if not multimedia:
        return EMPTY_IMAGE_FIELDS

    first = multimedia[0]
    rights = first.get("legal", {}).get("rights", [{}])[0] if first.get("legal", {}).get("rights") else {}
    licence = rights.get("licence", "")

    if open_licence_only and licence not in OPEN_LICENCES:
        return EMPTY_IMAGE_FIELDS

    location = first.get("@processed", {}).get("medium", {}).get("location", "")
    if not location:
        return EMPTY_IMAGE_FIELDS

    if download_images:
        image_path = f"images/{location}"
    else:
        image_path = f"{media_path}{location}"

    return {
        "image_path": image_path,
        "_remote_url": f"{media_path}{location}" if download_images else "",
        "_local_path": f"images/{location}" if download_images else "",
        "image_licence": licence,
        "image_copyright": rights.get("copyright", ""),
        "image_credit": first.get("credit", {}).get("value", ""),
    }


def format_epoch_ms(epoch_ms: Optional[int]) -> str:
    """Convert an epoch-millisecond timestamp to ISO date string, or empty string if missing."""
    if not epoch_ms:
        return ""
    try:
        return datetime.utcfromtimestamp(epoch_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, ValueError, TypeError):
        return ""


def extract_row(source: dict, base_url: str, media_path: Optional[str] = None, open_licence_only: bool = True, download_images: bool = False) -> dict:
    """Extract a single CSV row from an ES _source document."""
    admin = source.get("@admin", {})
    uid = admin.get("uid", "")
    title = get_primary_value(source.get("title"))
    summary_title = source.get("summary", {}).get("title", "") or title
    creation = source.get("creation", {})
    categories = source.get("category", [])
    cat_names = "; ".join(
        c.get("name", "") for c in categories if isinstance(c, dict) and c.get("name")
    )

    row = {
        "identifier": get_primary_value(source.get("identifier")),
        "uid": uid,
        "created": format_epoch_ms(admin.get("added")),
        "modified": format_epoch_ms(admin.get("processed")),
        "title": title,
        "object_name": get_object_name(source),
        "description": get_primary_value(source.get("description")),
        "date_made": get_creation_field(creation, "date"),
        "place_made": get_creation_field(creation, "place"),
        "maker": get_creation_field(creation, "maker"),
        "category": cat_names,
        "materials": get_materials(source),
        "measurements": get_measurements_display(source),
        "url": build_url(base_url, uid, summary_title),
    }

    if media_path is not None:
        image_fields = get_image_fields(source, media_path, open_licence_only, download_images)
        remote_url = image_fields.pop("_remote_url", "")
        local_path = image_fields.pop("_local_path", "")
        row.update(image_fields)
        row["_remote_url"] = remote_url
        row["_local_path"] = local_path

    return row


def export_objects(
    es: Elasticsearch,
    index: str,
    query: dict,
    base_url: str,
    output_path: str,
    batch_size: int = 1000,
    media_path: Optional[str] = None,
    open_licence_only: bool = True,
    download_images: bool = False,
) -> tuple:
    """Export matching objects to CSV using scroll API. Returns (row_count, downloads)."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    headers = IMAGE_CSV_HEADERS if media_path else CSV_HEADERS
    source_fields = IMAGE_SOURCE_FIELDS if media_path else SOURCE_FIELDS

    count = 0
    downloads = []
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()

        resp = es.search(
            index=index,
            query=query,
            _source=source_fields,
            scroll="5m",
            size=batch_size,
        )

        scroll_id = resp["_scroll_id"]
        hits = resp["hits"]["hits"]

        while hits:
            for hit in hits:
                row = extract_row(hit["_source"], base_url, media_path, open_licence_only, download_images)
                remote_url = row.pop("_remote_url", "")
                local_path = row.pop("_local_path", "")
                if remote_url and local_path:
                    downloads.append((remote_url, local_path))
                writer.writerow(row)
                count += 1
            if count % 5000 == 0:
                print(f"  {count} records exported...")

            resp = es.scroll(scroll_id=scroll_id, scroll="5m")
            scroll_id = resp["_scroll_id"]
            hits = resp["hits"]["hits"]

        try:
            es.clear_scroll(scroll_id=scroll_id)
        except Exception:
            pass  # Scroll expires naturally; some proxies block DELETE

    return count, downloads


def download_images(downloads: list, export_folder: str):
    """Download images to the export folder."""
    total = len(downloads)
    print(f"Downloading {total} images...")
    session = requests.Session()
    downloaded = 0
    failed = 0

    for remote_url, local_path in downloads:
        dest = os.path.join(export_folder, local_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        try:
            resp = session.get(remote_url, timeout=30)
            resp.raise_for_status()
            with open(dest, "wb") as f:
                f.write(resp.content)
            downloaded += 1
        except Exception as e:
            print(f"  Failed: {remote_url} ({e})")
            failed += 1

        if (downloaded + failed) % 100 == 0:
            print(f"  {downloaded + failed}/{total} images processed...")

    print(f"  Downloaded: {downloaded}, failed: {failed}")


def load_export_config(path: str) -> dict:
    """Load an export config JSON file."""
    with open(path, "r") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(
        description="Export data from the SMG Collections Online Elasticsearch index."
    )
    parser.add_argument(
        "export_config", nargs="?",
        help="Path to an export config JSON file (e.g. export_configs/railway_pre1976.json)",
    )
    parser.add_argument(
        "-c", "--config", default=".config",
        help="Path to server config file (default: .config)",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output folder path (default: exports/export_<timestamp>/)",
    )
    parser.add_argument(
        "--categories", nargs="+",
        help="Filter by category names (overrides export config)",
    )
    parser.add_argument(
        "--exclude-categories", nargs="+",
        help="Exclude these category names (overrides export config)",
    )
    parser.add_argument(
        "--before-year", type=int,
        help="Only include objects made before this year (overrides export config)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=1000,
        help="Scroll batch size (default: 1000)",
    )
    parser.add_argument(
        "--include-images", action="store_true",
        help="Include image path, licence, copyright, and credit columns",
    )
    parser.add_argument(
        "--all-image-licences", action="store_true",
        help="Include images with any licence (default: only open licences — CC and OGL)",
    )
    parser.add_argument(
        "--download-images", action="store_true",
        help="Download images to a local images/ folder within the export (implies --include-images)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show the query and estimated count without exporting",
    )

    args = parser.parse_args()

    # Load export config if provided, then let CLI args override
    export_cfg = {}
    if args.export_config:
        export_cfg = load_export_config(args.export_config)
        print(f"Using export config: {export_cfg.get('name', args.export_config)}")

    config = load_config(args.config)

    es_node = config.get("elasticsearch", "node")
    es_index = config.get("elasticsearch", "index")
    base_url = config.get("export", "base_url")
    output_dir = config.get("export", "output_dir", fallback="exports")

    categories = args.categories or export_cfg.get("categories", [])
    exclude_categories = args.exclude_categories or export_cfg.get("exclude_categories", [])
    before_year = args.before_year if args.before_year is not None else export_cfg.get("before_year")
    dl_images = args.download_images or export_cfg.get("download_images", False)
    include_images = args.include_images or export_cfg.get("include_images", False) or dl_images
    open_licence_only = not (args.all_image_licences or export_cfg.get("all_image_licences", False))

    timestamp = datetime.now().strftime("%Y%m%d")

    # Create timestamped export folder, using config filename if available
    if args.export_config:
        config_name = os.path.splitext(os.path.basename(args.export_config))[0]
        folder_name = f"{config_name}_{timestamp}"
    else:
        folder_name = f"export_{timestamp}"
    export_folder = args.output or os.path.join(output_dir, folder_name)
    os.makedirs(export_folder, exist_ok=True)
    output_path = os.path.join(export_folder, "objects.csv")

    query = build_query(categories, exclude_categories, before_year)

    es = create_es_client(es_node)

    if args.dry_run:
        print("Query:")
        print(json.dumps(query, indent=2))
        result = es.count(index=es_index, body={"query": query})
        print(f"\nMatching documents: {result['count']}")
        return

    print(f"Exporting to {export_folder}/")
    if categories:
        print(f"  Categories: {', '.join(categories)}")
    if exclude_categories:
        print(f"  Excluding: {', '.join(exclude_categories)}")
    if before_year is not None:
        print(f"  Made before: {before_year}")

    media_path = None
    if include_images:
        media_path = config.get("export", "media_path")
        licence_mode = "all" if not open_licence_only else "open only (CC / OGL)"
        print(f"  Including images: yes ({licence_mode})")
        if dl_images:
            print(f"  Downloading images: yes")

    count, downloads = export_objects(es, es_index, query, base_url, output_path, args.batch_size, media_path, open_licence_only, dl_images)

    if downloads:
        download_images(downloads, export_folder)

    # Write export summary
    summary_lines = []
    if export_cfg.get("name"):
        summary_lines.append(f"Export: {export_cfg['name']}")
    if export_cfg.get("description"):
        summary_lines.append(f"Description: {export_cfg['description']}")
    summary_lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    summary_lines.append(f"Records: {count}")
    summary_lines.append(f"Index: {es_index}")
    summary_lines.append(f"Source: Mimsy XG objects")
    if categories:
        summary_lines.append(f"Categories: {', '.join(categories)}")
    if exclude_categories:
        summary_lines.append(f"Excluded categories: {', '.join(exclude_categories)}")
    if before_year is not None:
        summary_lines.append(f"Made before: {before_year}")
    if include_images:
        summary_lines.append(f"Images: {licence_mode}")
        if dl_images:
            summary_lines.append(f"Images downloaded: {len(downloads)}")
    if args.export_config:
        summary_lines.append(f"Export config: {args.export_config}")
    summary_lines.append(f"Output: objects.csv")

    summary_path = os.path.join(export_folder, "export_info.txt")
    with open(summary_path, "w") as f:
        f.write("\n".join(summary_lines) + "\n")

    print(f"Done. Exported {count} records to {export_folder}/")


if __name__ == "__main__":
    main()
