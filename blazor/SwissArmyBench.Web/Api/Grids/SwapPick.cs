namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A swap that needs a pick: the table and the connections, where it was, the tables of its name in the other
/// connection, the other's schemas to browse, and its query (for Write a query…).</summary>
public sealed record SwapPick(
    string Table,
    string To,
    string? From,
    SwapPlace Was,
    IReadOnlyList<SwapPlace> Candidates,
    IReadOnlyList<SwapSchema> Schemas,
    string Sql);
