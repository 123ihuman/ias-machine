import csv
import os
import sys
import json
import requests

DATA_URL = "https://dataful.in/datasets/19768/download.csv"  # update if URL changes

def download_csv(path="toppers_raw.csv"):
    r = requests.get(DATA_URL)
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)
    return path

def main():
    print("Downloading dataset...")
    csv_path = download_csv()
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    # Group by year+rank to merge stage rows
    merged = {}
    for row in rows:
        key = (row.get("exam_year"), row.get("rank"), row.get("roll_number"))
        if key not in merged:
            merged[key] = {
                "year": row.get("exam_year"),
                "rank": row.get("rank"),
                "roll_no": row.get("roll_number"),
                "name": row.get("recommended_candidate_name"),
                "category": row.get("category"),
                "written": None,
                "interview": None,
                "total": None,
            }
        et = (row.get("exam_type") or "").lower()
        try:
            marks = float(row.get("marks") or 0)
        except ValueError:
            marks = None
        if "written" in et and "total" not in et:
            merged[key]["written"] = marks
        elif "interview" in et and "total" not in et:
            merged[key]["interview"] = marks
        elif "final" in et:
            merged[key]["total"] = marks

    with open("toppers_clean.json", "w") as f:
        json.dump(list(merged.values()), f, indent=2)
    print(f"Saved {len(merged)} toppers to toppers_clean.json")

if __name__ == "__main__":
    main()