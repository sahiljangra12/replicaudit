data = pd.read_parquet(os.path.join(os.environ["WORK_DIR"], "analysis.parquet"))
model = sm.OLS(data['y'], sm.add_constant(data[['x', 'z', 'w']])).fit()
b = model.params['x']
se = model.bse['x']
print("RESULT_JSON: {\"b\": {b}, \"se\": {se}, \"n\": {len(data)}}")