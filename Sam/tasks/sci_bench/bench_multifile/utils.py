"""Helper functions for the project."""

import json
import os


def format_output(data, fmt="json"):
    """Format *data* (list of dicts) as a string.

    Parameters
    ----------
    data : list[dict]
    fmt  : str, "json" or "csv"

    Returns
    -------
    str
    """
    if fmt == "json":
        return json.dumps(data, indent=2)
    elif fmt == "csv":
        if not data:
            return ""
        header = ",".join(data[0].keys())
        rows = [",".join(str(v) for v in row.values()) for row in data]
        return header + "\n" + "\n".join(rows)
    else:
        raise ValueError(f"Unknown format: {fmt}")


def validate_input(path):
    """Return True if *path* exists and ends with .csv."""
    return os.path.isfile(path) and path.endswith(".csv")
