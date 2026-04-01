# Collections Exporter

Command-line tool to export data from the Science Museum Group Collections Online Elasticsearch index.

## Setup

### Prerequisites

- Python 3.10+
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
node = http://user:pass@your-es-host:9200
index = ciim

[export]
output_dir = exports
base_url = https://collection.sciencemuseumgroup.org.uk
```

## Usage

### Basic export (default filters)

Exports Mimsy object records in the "Passenger Comforts" and "Railway Models" categories, made before 1976:

```bash
python exporter.py
```

Output: `exports/objects_export.csv`

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

### Dry run

Preview the query and document count without exporting:

```bash
python exporter.py --dry-run
```

### All options

```
usage: exporter.py [-h] [-c CONFIG] [-o OUTPUT] [--categories CATEGORIES [CATEGORIES ...]]
                   [--before-year BEFORE_YEAR] [--no-date-filter] [--no-category-filter]
                   [--batch-size BATCH_SIZE] [--dry-run]

options:
  -h, --help            show this help message and exit
  -c, --config CONFIG   Path to config file (default: .config)
  -o, --output OUTPUT   Output CSV file path (default: exports/objects_export.csv)
  --categories          Category names to filter by (default: 'Passenger Comforts' 'Railway Models')
  --before-year         Only include objects made before this year (default: 1976)
  --no-date-filter      Disable the date filter
  --no-category-filter  Disable the category filter
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
| date_made | Creation date (role: made) |
| place_made | Creation place (role: made) |
| maker | Creation maker (role: made) |
| category | Category names (semicolon-separated) |
| materials | Material values (semicolon-separated) |
| measurements | Measurements display string |
| url | Public collection URL |
