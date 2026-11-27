import os
import pandas as pd
import json

# Load the dataset
data = pd.read_parquet(os.path.join(os.environ["WORK_DIR"], "analysis.parquet"))

# Fit the linear regression model
model = sm.OLS(data['y'], sm.add_constant(data[['x', 'z']])).fit()

# Extract the coefficient and standard error
b = model.params['x']
se = model.bse['x']

# Print the result in JSON format
print("RESULT_JSON: " + json.dumps({"b": b, "se": se, "n": len(data)}))
