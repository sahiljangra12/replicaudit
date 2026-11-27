import json, os, warnings
import pandas as pd
import pyfixest as pf
warnings.filterwarnings("ignore")
df = pd.read_parquet(os.path.join(os.environ["WORK_DIR"], "analysis.parquet"))
df['BNbin'] = pd.cut(df['BN'], [0,1,2,3,5,10,20,50,1e9]).cat.codes
d = df
# reghdfe ShannonBD PI Temp Wind Pop Duration Carbon Water Green Farm Grass, absorb(county ym BNbin) cluster(...)
m = pf.feols("ShannonBD ~ PI + Temp + Wind + Pop + Duration + Carbon + Water + Green + Farm + Grass | county + ym + BNbin", d, vcov={"CRV1": "county"}, fixef_rm="singleton")
print("RESULT_JSON: " + json.dumps({"b": float(m.coef()["PI"]), "se": float(m.se()["PI"]), "n": int(m._N)}))
