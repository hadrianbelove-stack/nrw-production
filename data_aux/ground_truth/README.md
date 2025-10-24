# Ground Truth Data for Discovery Validation

This directory contains curated ground truth data for validating the discovery system's performance.

## File Format

Each weekly ground truth file follows the pattern `YYYY-WW.yaml` where:
- `YYYY` is the year (4 digits)
- `WW` is the ISO week number (2 digits, zero-padded)

## Structure

```yaml
week: "2024-42"
start_date: "2024-10-14"
end_date: "2024-10-20"
movies:
  - title: "Movie Title"
    date: "2024-10-15"
    tmdb_id: "12345"  # Optional
    notes: "Any relevant notes"  # Optional
```

## Usage

The validation harness (`ops/validate_discovery.py`) loads ground truth data for the specified time period and compares it against discovered movies to calculate:

- **Recall**: What percentage of ground truth movies were discovered
- **Precision**: What percentage of discovered movies are in ground truth
- **F1 Score**: Harmonic mean of recall and precision

## Creating Ground Truth Files

1. Manually research what movies went digital during a given week
2. Create a YAML file with the appropriate week number
3. List all movies that should have been discovered
4. Include accurate release dates and titles

## Example

```yaml
week: "2024-42"
start_date: "2024-10-14"
end_date: "2024-10-20"
movies:
  - title: "Terrifier 3"
    date: "2024-10-15"
    tmdb_id: "1034541"
  - title: "The Wild Robot"
    date: "2024-10-17"
    tmdb_id: "1184918"
```