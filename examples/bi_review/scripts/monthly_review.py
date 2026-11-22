"""The month's headline figures from the warehouse (made-up data: Larkfield Goods)."""

import swissarmybench as sab

# %% [1] Orders per channel
by_channel = sab.sql(
    "Larkfield Warehouse",
    "SELECT channel, count(*) AS orders FROM orders GROUP BY channel ORDER BY channel",
)
print(by_channel)

# %% [2] The headline
headline = {"channels": len(by_channel), "orders": int(by_channel["orders"].sum())}
print(headline)
