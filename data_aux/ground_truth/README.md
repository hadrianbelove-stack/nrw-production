# Ground Truth Data for Discovery Validation

This directory contains curated ground truth data for validating the NRW provider-availability discovery performance.

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

This ground truth data was previously used by a validation harness (`ops/validate_discovery.py`) that compared discovered movies against manually curated data. The validation system has been removed from the automated pipeline as it lacked current ground truth data and provided limited value.

The ground truth framework could potentially be used for:
- Manual validation of NRW provider-availability discovery quality
- One-off analysis of recall and precision metrics
- Research into NRW system performance

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