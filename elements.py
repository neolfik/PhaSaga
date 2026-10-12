import csv
from typing import Dict

ELEMENTS: Dict[str, dict] = {}

## Creates a global variable containing elements information neccessary for calculation and checks
# during the analysis process
def load_elements(csv_file: str) -> None:
    global ELEMENTS
    ELEMENTS.clear()
    with open(csv_file, newline='', encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            short = row["Short"].strip()
            ELEMENTS[short] = {
                "name": row["Name"].strip(),
                "weight": float(row["Weight"]),
            }
