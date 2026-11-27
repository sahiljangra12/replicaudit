import json, os, warnings
import pandas as pd
import pyfixest as pf
warnings.filterwarnings("ignore")
df = pd.read_parquet(os.path.join(os.environ["WORK_DIR"], "analysis.parquet"))
d = df
# reghdfe PI Sun_ccpu Temp Wind Pop Duration Carbon Water Green Farm Grass, absorb(county ym) cluster(...)
m = pf.feols("PI ~ Sun_ccpu + Temp + Wind + Pop + Duration + Carbon + Water + Green + Farm + Grass | county + ym", d, vcov={"CRV1": "county"}, fixef_rm="none")
print("RESULT_JSON: " + json.dumps({"b": float(m.coef()["Sun_ccpu"]), "se": float(m.se()["Sun_ccpu"]), "n": int(m._N)}))
