import os
import pandas as pd

def get_json_from_dataset(query: str) -> list:
    gdelt_dir = os.path.join("dataset", "gdelt_dataset")

    csv_files = [
        os.path.join(gdelt_dir, f)
        for f in os.listdir(gdelt_dir)
        if f.lower().endswith(".csv")
    ]

    filtered_frames = []

    for csv_file in csv_files:
        df = pd.read_csv(csv_file)
        mask = df.astype(str).apply(
            lambda col: col.str.contains(query, case=False, na=False)
        ).any(axis=1)
        filtered_frames.append(df[mask])

    result = pd.concat(filtered_frames, ignore_index=True) if filtered_frames else pd.DataFrame()
    data = result.head(200)
    # Convert to the desired JSON format
    json_data = []
    for _, row in data.iterrows():
        json_data.append({
            "date": row['Date'],
            "title": row['Title'],
            "description": row['Description'],
            "url": row['Link']
        })
    return json_data