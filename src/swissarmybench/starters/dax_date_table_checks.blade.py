# /// swissarmybench-blade
# format = 1
# name = "DAX date table checks"
# kind = "snippet"
# description = "Days missing from a date table, and days listed twice"
# tags = ["dax", "checks"]
# family = "DAX"
# language = "dax"
# ///
snippet = r"""
-- Date table checks: time intelligence (TOTALYTD, SAMEPERIODLASTYEAR) needs every day once, from the
-- first date to the last. "Missing days" and "Repeated days" should both be 0.
-- For the list of missing days, end with: RETURN Missing
EVALUATE
VAR FirstDay = MIN ( '<<date table>>'[<<date column>>] )
VAR LastDay = MAX ( '<<date table>>'[<<date column>>] )
VAR Listed = DISTINCT ( '<<date table>>'[<<date column>>] )
VAR Missing = EXCEPT ( SELECTCOLUMNS ( CALENDAR ( FirstDay, LastDay ), "Day", [Date] ), Listed )
VAR Repeated =
    FILTER (
        ADDCOLUMNS ( Listed, "Times", CALCULATE ( COUNTROWS ( '<<date table>>' ) ) ),
        [Times] > 1
    )
RETURN
    ROW (
        "First day", FirstDay,
        "Last day", LastDay,
        "Days listed", COUNTROWS ( Listed ),
        "Missing days", COUNTROWS ( Missing ) + 0,
        "Repeated days", COUNTROWS ( Repeated ) + 0
    )
"""
