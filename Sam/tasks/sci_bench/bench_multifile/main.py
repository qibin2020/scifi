"""Main entry point for the data-processing project.

DataProcessor lives here initially.  A refactoring benchmark will move it
to models.py while keeping all tests green.
"""

import csv

from utils import format_output, validate_input
import config


class DataProcessor:
    """Load, filter, and summarize CSV data."""

    def __init__(self):
        self.data = []

    def load(self, path):
        """Load rows from a CSV file at *path*.

        Each row becomes a dict with keys matching the CSV header.
        The 'score' column (if present) is cast to float.
        """
        if not validate_input(path):
            raise FileNotFoundError(f"Invalid or missing file: {path}")
        with open(path, newline="") as fh:
            reader = csv.DictReader(fh)
            self.data = []
            for row in reader:
                if "score" in row:
                    row["score"] = float(row["score"])
                self.data.append(row)
        return self.data

    def filter(self, threshold=None):
        """Return rows whose score exceeds *threshold*.

        Uses ``config.THRESHOLD`` when *threshold* is None.
        """
        if threshold is None:
            threshold = config.THRESHOLD
        return [row for row in self.data if row.get("score", 0) > threshold]

    def summarize(self):
        """Return summary statistics for loaded data.

        Returns
        -------
        dict with keys: count, mean_score, max_score, min_score.
        """
        if not self.data:
            return {"count": 0, "mean_score": 0, "max_score": 0, "min_score": 0}
        scores = [row["score"] for row in self.data if "score" in row]
        if not scores:
            return {"count": len(self.data), "mean_score": 0, "max_score": 0, "min_score": 0}
        return {
            "count": len(self.data),
            "mean_score": round(sum(scores) / len(scores), 2),
            "max_score": max(scores),
            "min_score": min(scores),
        }


if __name__ == "__main__":
    proc = DataProcessor()
    proc.load(config.DATA_PATH)
    above = proc.filter()
    summary = proc.summarize()
    print(format_output([summary], config.OUTPUT_FORMAT))
