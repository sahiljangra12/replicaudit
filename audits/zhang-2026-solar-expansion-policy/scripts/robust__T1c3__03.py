import json, os, warnings
import pandas as pd
import pyfixest as pf
warnings.filterwarnings("ignore")
df = pd.read_parquet(os.path.join(os.environ["WORK_DIR"], "analysis.parquet"))
import numpy as np
df['lnBT'] = np.log(df['BT'] + 1)
d = df
# reghdfe ShannonBD PI Temp Wind Pop Duration Carbon Water Green Farm Grass lnBT, absorb(county ym) cluster(...)
m = pf.feols("ShannonBD ~ PI + Temp + Wind + Pop + Duration + Carbon + Water + Green + Farm + Grass + lnBT | county + ym", d, vcov={"CRV1": "county"}, fixef_rm="singleton")
print("RESULT_JSON: " + json.dumps({"b": float(m.coef()["PI"]), "se": float(m.se()["PI"]), "n": int(m._N)}))
