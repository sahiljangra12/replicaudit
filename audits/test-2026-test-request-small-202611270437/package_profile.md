## Data files
- data.csv  rows=300  columns: y:float64, x:float64, z:float64

## Code files
- README.md (372 bytes)
- main.R (135 bytes)

## Code contents
===== README.md =====
# Test package

A tiny replication package with simulated data, used to check that ReplicAudit works end to end.
`main.R` regresses y on x and z (n = 300). Expected estimates: x = 0.386 (SE 0.061), z = -0.278 (SE 0.061).

To try it on the website, paste this folder's link as the data and code:
https://github.com/sahiljangra12/replicaudit/tree/main/examples/test-package


===== main.R =====
# Test replication package for ReplicAudit: Table 1, column 1
d <- read.csv("data.csv")
m <- lm(y ~ x + z, data = d)
print(summary(m))
