# Test replication package for ReplicAudit: Table 1, column 1
d <- read.csv("data.csv")
m <- lm(y ~ x + z, data = d)
print(summary(m))
