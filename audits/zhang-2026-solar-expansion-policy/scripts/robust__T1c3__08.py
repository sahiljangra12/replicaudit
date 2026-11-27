import json, os, warnings
import pandas as pd
import pyfixest as pf
warnings.filterwarnings("ignore")
df = pd.read_parquet(os.path.join(os.environ["WORK_DIR"], "analysis.parquet"))
d = df
# reghdfe ShannonBD PI Temp Wind Pop Duration Carbon Water Green Farm Grass, absorb(county prov_ym) cluster(...)
m = pf.feols("ShannonBD ~ PI + Temp + Wind + Pop + Duration + Carbon + Water + Green + Farm + Grass | county + prov_ym", d, vcov={"CRV1": "county"}, fixef_rm="singleton")
print("RESULT_JSON: " + json.dumps({"b": float(m.coef()["PI"]), "se": float(m.se()["PI"]), "n": int(m._N)}))
