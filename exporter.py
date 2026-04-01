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
    return get_primary_value(dimensions)


def get_object_name(source: dict) -> str:
    """Extract the primary object name from name array."""
    return get_primary_value(source.get("name", []))


def build_url(base_url: str, uid: str, title: str) -> str:
    """Build the public collection URL for an object."""
    slug = slugify(title) if title else ""
    return f"{base_url}/objects/{uid}/{slug}"


def build_query(categories: list, before_year: Optional[int]) -> dict:
    """Build the ES query for Mimsy object records with given filters."""
    must = [
        {"term": {"@admin.source": "Mimsy XG"}},
        {"term": {"@datatype.base": "object"}},
    ]

    if categories:
        must.append({"terms": {"category.name.keyword": categories}})

    if before_year is not None:
        must.append({"range": {"creation.date.to": {"lt": str(before_year)}}})

    return {"bool": {"must": must}}


SOURCE_FIELDS = [
    "@admin.uid",
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


def get_image_fields(source: dict, media_path: str) -> dict:
    """Extract first multimedia medium image path and legal fields."""
    multimedia = source.get("multimedia", [])
    if not multimedia:
        return {"image_path": "", "image_licence": "", "image_copyright": "", "image_credit": ""}

    first = multimedia[0]
    location = first.get("@processed", {}).get("medium", {}).get("location", "")
    rights = first.get("legal", {}).get("rights", [{}])[0] if first.get("legal", {}).get("rights") else {}

    return {
        "image_path": f"{media_path}{location}" if location else "",
        "image_licence": rights.get("licence", ""),
        "image_copyright": rights.get("copyright", ""),
        "image_credit": first.get("credit", {}).get("value", ""),
    }


def extract_row(source: dict, base_url: str, media_path: Optional[str] = None) -> dict:
    """Extract a single CSV row from an ES _source document."""
    uid = source.get("@admin", {}).get("uid", "")
    title = get_primary_value(source.get("title"))
    summary_title = source.get("summary", {}).get("title", "") or title
    creation = source.get("creation", {})
    categories = source.get("category", [])
    cat_names = "; ".join(
        c.get("name", "") for c in categories if isinstance(c, dict) and c.get("name")
    )

    row = {
        "identifier": get_primary_value(source.get("identifier")),
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
        row.update(get_image_fields(source, media_path))

    return row


def export_objects(
    es: Elasticsearch,
    index: str,
    query: dict,
    base_url: str,
    output_path: str,
    batch_size: int = 1000,
    media_path: Optional[str] = None,
) -> int:
    """Export matching objects to CSV using scroll API. Returns row count."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    headers = IMAGE_CSV_HEADERS if media_path else CSV_HEADERS
    source_fields = IMAGE_SOURCE_FIELDS if media_path else SOURCE_FIELDS

    count = 0
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
                row = extract_row(hit["_source"], base_url, media_path)
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

    return count


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
        help="Output CSV file path (overrides export config)",
    )
    parser.add_argument(
        "--categories", nargs="+",
        help="Filter by category names (overrides export config)",
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
    before_year = args.before_year if args.before_year is not None else export_cfg.get("before_year")
    include_images = args.include_images or export_cfg.get("include_images", False)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_filename = f"objects_export_{timestamp}.csv"
    output_path = args.output or export_cfg.get("output") or os.path.join(output_dir, default_filename)

    query = build_query(categories, before_year)

    es = create_es_client(es_node)

    if args.dry_run:
        print("Query:")
        print(json.dumps(query, indent=2))
        result = es.count(index=es_index, body={"query": query})
        print(f"\nMatching documents: {result['count']}")
        return

    print(f"Exporting objects to {output_path}...")
    if categories:
        print(f"  Categories: {', '.join(categories)}")
    if before_year is not None:
        print(f"  Made before: {before_year}")

    media_path = None
    if include_images:
        media_path = config.get("export", "media_path")
        print(f"  Including images: yes")

    count = export_objects(es, es_index, query, base_url, output_path, args.batch_size, media_path)
    print(f"Done. Exported {count} records to {output_path}")


if __name__ == "__main__":
    main()
