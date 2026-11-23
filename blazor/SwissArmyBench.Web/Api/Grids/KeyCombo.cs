namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A combination of columns: how many distinct combinations, their share of the rows, the rows that repeat
/// an earlier one, whether it tells every row apart.</summary>
public sealed record KeyCombo(IReadOnlyList<string> Columns, long Distinct, double Share, long RepeatedRows, bool Unique);
