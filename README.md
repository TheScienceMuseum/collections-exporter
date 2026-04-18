# Collections Exporter

Command-line tool to export data from the Science Museum Group Collections Online Elasticsearch index to CSV.

## Setup

### Prerequisites

- Python 3.9+
- Access to the Collections Online Elasticsearch instance

### Install

```bash
cd collections-exporter
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure

Copy the template config and fill in your ES credentials:

```bash
cp .config.template .config
```

Edit `.config` with your Elasticsearch connection details:

```ini
[elasticsearch]
node = http://user:pass@your-es-host/path-prefix/
index = ciim

[export]
output_dir = exports
base_url = https://collection.sciencemuseumgroup.org.uk
media_path = https://coimages.sciencemuseumgroup.org.uk/
```

> **Note:** If your ES instance is behind a reverse proxy on port 80 (no port in the URL), the client handles this automatically — no need to specify `:80`.

## Usage

### Export configs

The simplest way to run an export is with an export config file. These are JSON files in `export_configs/` that define the filters and options for a particular export:

```bash
python exporter.py export_configs/railway_pre1976.json
```

An export config looks like this:

```json
{
  "name": "Railway objects pre-1976",
  "description": "Passenger Comforts and Railway Models made before 1976",
  "categories": ["Passenger Comforts", "Railway Models"],
  "before_year": 1976,
  "include_images": true
}
```

Available fields:

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Display name shown when the export runs |
| `description` | string | Human-readable description of the export |
| `categories` | string[] | Category names to filter by |
| `exclude_categories` | string[] | Category names to exclude |
| `before_year` | int | Only include objects made before this year |
| `include_images` | bool | Include image path, licence, copyright, and credit columns |
| `all_image_licences` | bool | Include images with any licence (default: only open licences) |
| `download_images` | bool | Download images locally (implies `include_images`) |
| `output` | string | Output folder path (overrides default timestamped folder) |

To create a new export, add a JSON file to `export_configs/` and run it:

```bash
python exporter.py export_configs/my_export.json
```

### CLI overrides

Any CLI argument will override the corresponding export config value:

```bash
# Use config but override the date filter
python exporter.py export_configs/railway_pre1976.json --before-year 2000

# Use config but send output to a specific folder
python exporter.py export_configs/railway_pre1976.json -o my_export_folder
```

### Running without an export config

You can also run directly with CLI arguments:

```bash
# Export all Mimsy objects
python exporter.py

# Filter by category and date
python exporter.py --categories "Passenger Comforts" "Railway Models" --before-year 1976

# Exclude specific categories
python exporter.py --exclude-categories "Photographs" "Art"

# Include image data (open licences only by default)
python exporter.py --categories "Railway Models" --include-images

# Include images with any licence
python exporter.py --categories "Railway Models" --include-images --all-image-licences

# Download images locally
python exporter.py --categories "Railway Models" --download-images
```

### Download images

Use `--download-images` to save images into a local `images/` folder within the export. The `image_path` column in the CSV will reference local paths instead of remote URLs:

```bash
python exporter.py --categories "Railway Models" --before-year 1850 --download-images
```

This produces:

```
exports/export_20260401_140513/
├── objects.csv          # image_path = images/288/534/medium_image.jpg
├── export_info.txt
└── images/
    ├── 288/534/medium_image.jpg
    ├── 105/964/medium_other.jpg
    └── ...
```

### Dry run

Preview the query and document count without exporting:

```bash
python exporter.py export_configs/railway_pre1976.json --dry-run
```

### All options

```
usage: exporter.py [-h] [-c CONFIG] [-o OUTPUT] [--categories CATEGORIES [CATEGORIES ...]]
                   [--exclude-categories EXCLUDE [EXCLUDE ...]]
                   [--before-year BEFORE_YEAR] [--include-images] [--all-image-licences]
                   [--download-images] [--batch-size BATCH_SIZE] [--dry-run]
                   [export_config]

positional arguments:
  export_config           Path to an export config JSON file

options:
  -h, --help              show this help message and exit
  -c, --config CONFIG     Path to server config file (default: .config)
  -o, --output OUTPUT     Output folder path (default: exports/export_<timestamp>/)
  --categories            Filter by category names (overrides export config)
  --exclude-categories    Exclude these category names (overrides export config)
  --before-year           Only include objects made before this year (overrides export config)
  --include-images        Include image path, licence, copyright, and credit columns
  --all-image-licences    Include images with any licence (default: only open licences)
  --download-images       Download images locally (implies --include-images)
  --batch-size            Scroll batch size (default: 1000)
  --dry-run               Show the query and estimated count without exporting
```

## Output

Each export creates a timestamped folder:

```
exports/export_20260401_120000/
├── objects.csv        # the exported data
└── export_info.txt    # summary of settings and record count
```

## CSV Output Fields

| Field | Source |
|-------|--------|
| identifier | Primary identifier (accession number) |
| uid | Collection record ID (e.g. co12345) |
| created | Record created date (UTC) |
| modified | Record last modified date (UTC) |
| title | Primary title |
| object_name | Primary name |
| description | Primary description |
| date_made | Creation date (catalogue entry) |
| place_made | Creation place (catalogue entry) |
| maker | Creation maker (catalogue entry) |
| category | Category names (semicolon-separated) |
| materials | Material values (semicolon-separated) |
| measurements | Measurements display string |
| url | Public collection URL |

With `--include-images` or `--download-images`:

| Field | Source |
|-------|--------|
| image_path | URL to medium image, or local path if downloading |
| image_licence | Image licence (e.g. CC BY-NC-SA 4.0) |
| image_copyright | Image copyright holder |
| image_credit | Image credit line |
