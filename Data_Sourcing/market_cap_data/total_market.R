install.packages("crypto2")
library(crypto2)

g <- crypto_global_quotes(which = "historical", quote = TRUE)
write.csv(g, "total_market_cap.csv", row.names = FALSE)