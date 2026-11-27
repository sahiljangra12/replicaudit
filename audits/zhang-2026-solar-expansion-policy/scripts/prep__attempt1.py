import json
import os

import numpy as np
import pandas as pd

D = os.path.join(os.environ["PACKAGE_DIR"], "DATA")


def rd(name, cols=None):
    df = pd.read_stata(os.path.join(D, name + ".dta"))
    return df if cols is None else df[cols]


def m(left, right, on):
    # Stata merge, keeping master rows (drop if _merge==2); using must be unique on keys
    assert not right.duplicated(on).any(), f"non-unique keys {on}"
    return left.merge(right, on=on, how="left", validate="m:1")


df = rd("Bird")
df = m(df, rd("BTN", ["id", "year", "BT", "BN"]), ["id", "year"])
df = m(df, rd("PI", ["id", "YEAR", "PI"]), ["id", "YEAR"])
df = m(df, rd("Climate", ["id", "YEAR", "Avt", "Wind"]).rename(columns={"Avt": "Temp"}), ["id", "YEAR"])
df = m(df, rd("PD", ["id", "YEAR", "PD"]), ["id", "YEAR"])
df = m(df, rd("air", ["id", "YEAR", "CO2", "PM"]).rename(columns={"PM": "PM25"}), ["id", "YEAR"])
df = m(df, rd("TD", ["id", "YEAR", "Water", "Green", "Farm", "Grass"]), ["id", "YEAR"])

sun = rd("sunshine", ["id", "YEAR", "sun"]).drop_duplicates()
df = m(df, sun, ["id", "YEAR"])
df = m(df, rd("CCPU", ["市", "YEAR", "CCPU"]), ["市", "YEAR"])

nd = rd("Ndvi", ["id", "YEAR", "Ndvi"])
df = m(df, nd, ["id", "YEAR"])
df["Ndvi"] = (df["Ndvi"].astype("float64") * 100).astype("float32")
df = m(df, rd("NL", ["id", "YEAR", "Nightlight"]), ["id", "YEAR"])
df = m(df, rd("LAI", ["id", "YEAR", "LAI"]), ["id", "YEAR"])

f32 = lambda s: s.astype("float64").astype("float32")  # Stata `gen` creates float variables
df["BTN"] = f32(df["BT"].astype("float64") / df["BN"].astype("float64"))
df["PI"] = df["PI"].fillna(0)
df = df.dropna(subset=["Temp", "Wind", "PD", "BTN", "CO2", "Water", "Green", "Farm", "Grass"]).copy()

df["Pop"] = f32(np.log(df["PD"].astype("float64")))
df["Duration"] = f32(np.log(df["BTN"].astype("float64") + 1))
df["Carbon"] = f32(np.log(df["CO2"].astype("float64")))


def stata_pctile(x, p):
    # Stata _pctile default definition (used by winsor2)
    x = np.sort(x[~np.isnan(x)])
    n = len(x)
    np_ = n * p / 100.0
    i = int(np.floor(np_))
    if abs(np_ - i) < 1e-9:
        return (x[i - 1] + x[i]) / 2.0
    return x[int(np.ceil(np_)) - 1]


wins = ["ShannonBD", "SimpsonBD", "PI", "Temp", "Wind", "Pop", "Duration", "Carbon", "Water", "Green",
        "Farm", "Grass", "Ndvi", "Nightlight", "LAI", "sun", "CCPU"]
df["ShannonBD_raw"] = df["ShannonBD"]
df["Duration_raw"] = df["Duration"]
for v in wins:
    x = df[v].astype("float64").to_numpy()
    lo, hi = stata_pctile(x, 1), stata_pctile(x, 99)
    y = np.where(np.isnan(x), np.nan, np.clip(x, lo, hi))
    df[v] = y.astype(df[v].dtype) if str(df[v].dtype).startswith("float") else y

df["lnsun"] = f32(np.log(df["sun"].astype("float64")))
df["Sun_ccpu"] = f32(df["lnsun"].astype("float64") / df["CCPU"].astype("float64"))
df["county"] = df.groupby("id").ngroup() + 1
df["ym"] = df["year"].astype("int64")  # year-month (Stata date) fixed effect
df["city"] = df.groupby("市").ngroup() + 1
df["prov"] = df.groupby("省").ngroup() + 1
df["prov_ym"] = df["prov"].astype("int64") * 10**6 + df.groupby("ym").ngroup()

keep = [c for c in df.columns if c not in ("year", "标准年月")]
out = df[keep].reset_index(drop=True)
out.to_parquet(os.path.join(os.environ["WORK_DIR"], "analysis.parquet"), index=False)
print("RESULT_JSON: " + json.dumps({"rows": len(out), "cols": out.shape[1]}))
