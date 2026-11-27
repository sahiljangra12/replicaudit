data = pd.read_parquet(os.path.join(os.environ["WORK_DIR"], "analysis.parquet"))
data = data.sample(frac=0.5, random_state=42)
model = sm.OLS(data['y'], sm.add_constant(data[['x', 'z']])).fit()
b = model.params['x']
se = model.bse['x']
print("RESULT_JSON: {\"b\": {b}, \"se\": {se}, \"n\": {len(data)}}")