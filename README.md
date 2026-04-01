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
| `before_year` | int | Only include objects made before this year |
| `include_images` | bool | Include image path, licence, copyright, and credit columns |
| `output` | string | Output file path (overrides default timestamped name) |

To create a new export, add a JSON file to `export_configs/` and run it:

```bash
python exporter.py export_configs/my_export.json
```

### CLI overrides

Any CLI argument will override the corresponding export config value:

```bash
# Use config but override the date filter
python exporter.py export_configs/railway_pre1976.json --before-year 2000

# Use config but send output to a specific file
python exporter.py export_configs/railway_pre1976.json -o custom_output.csv
```

### Running without an export config

You can also run directly with CLI arguments:

```bash
# Export all Mimsy objects
python exporter.py

# Filter by category and date
python exporter.py --categories "Passenger Comforts" "Railway Models" --before-year 1976

# Include image data
python exporter.py --categories "Railway Models" --include-images
```

### Dry run

Preview the query and document count without exporting:

```bash
python exporter.py export_configs/railway_pre1976.json --dry-run
```

### All options

```
usage: exporter.py [-h] [-c CONFIG] [-o OUTPUT] [--categories CATEGORIES [CATEGORIES ...]]
                   [--before-year BEFORE_YEAR] [--include-images]
                   [--batch-size BATCH_SIZE] [--dry-run]
                   [export_config]

positional arguments:
  export_config         Path to an export config JSON file (e.g. export_configs/railway_pre1976.json)

options:
  -h, --help            show this help message and exit
  -c, --config CONFIG   Path to server config file (default: .config)
  -o, --output OUTPUT   Output CSV file path (overrides export config)
  --categories          Filter by category names (overrides export config)
  --before-year         Only include objects made before this year (overrides export config)
  --include-images      Include image path, licence, copyright, and credit columns
  --batch-size          Scroll batch size (default: 1000)
  --dry-run             Show the query and estimated count without exporting
```

Output files are timestamped by default: `exports/objects_export_20260401_120000.csv`

## CSV Output Fields

| Field | Source |
|-------|--------|
| identifier | Primary identifier (accession number) |
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

With `--include-images` or `"include_images": true`:

| Field | Source |
|-------|--------|
| image_path | Full URL to medium-sized image |
| image_licence | `multimedia[0].legal.rights[0].licence` |
| image_copyright | `multimedia[0].legal.rights[0].copyright` |
| image_credit | `multimedia[0].credit.value` |
