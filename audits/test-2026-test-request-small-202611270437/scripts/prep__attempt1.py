import os
import pandas as pd
import json

# Load data
data_path = os.path.join(os.environ["PACKAGE_DIR"], "data.csv")
df = pd.read_csv(data_path)

# Save the analysis dataset
analysis_path = os.path.join(os.environ["WORK_DIR"], "analysis.parquet")
df.to_parquet(analysis_path)

# Print the result JSON
print("RESULT_JSON: " + json.dumps({"rows": len(df), "cols": df.shape[1]}))
