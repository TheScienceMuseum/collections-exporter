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

### Basic export (default filters)

Exports Mimsy object records in the "Passenger Comforts" and "Railway Models" categories, made before 1976:

```bash
python exporter.py
```

Output files are timestamped: `exports/objects_export_20260401_120000.csv`

### Custom output path

```bash
python exporter.py -o my_export.csv
```

### Custom filters

```bash
# Different categories
python exporter.py --categories "Locomotives" "Rolling Stock"

# Different date cutoff
python exporter.py --before-year 2000

# No date filter
python exporter.py --no-date-filter

# No category filter
python exporter.py --no-category-filter

# Export everything (no filters)
python exporter.py --no-category-filter --no-date-filter
```

### Include image data

Add `--include-images` to append image path, licence, copyright, and credit columns for the first image on each record:

```bash
python exporter.py --include-images
```

### Dry run

Preview the query and document count without exporting:

```bash
python exporter.py --dry-run
```

### All options

```
usage: exporter.py [-h] [-c CONFIG] [-o OUTPUT] [--categories CATEGORIES [CATEGORIES ...]]
                   [--before-year BEFORE_YEAR] [--no-date-filter] [--no-category-filter]
                   [--include-images] [--batch-size BATCH_SIZE] [--dry-run]

options:
  -h, --help            show this help message and exit
  -c, --config CONFIG   Path to config file (default: .config)
  -o, --output OUTPUT   Output CSV file path (default: exports/objects_export_<timestamp>.csv)
  --categories          Category names to filter by (default: 'Passenger Comforts' 'Railway Models')
  --before-year         Only include objects made before this year (default: 1976)
  --no-date-filter      Disable the date filter
  --no-category-filter  Disable the category filter
  --include-images      Include image path, licence, copyright, and credit columns
  --batch-size          Scroll batch size (default: 1000)
  --dry-run             Show the query and estimated count without exporting
```

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

With `--include-images`:

| Field | Source |
|-------|--------|
| image_path | Full URL to medium-sized image |
| image_licence | `multimedia[0].legal.rights[0].licence` |
| image_copyright | `multimedia[0].legal.rights[0].copyright` |
| image_credit | `multimedia[0].credit.value` |
