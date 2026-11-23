namespace SwissArmyBench.Web.Api.Catalog;

/// <summary>A connection's table as the Catalog's detail side shows it (GET /explorer/table): where it comes from,
/// its SQL name, its columns, the code that reads it, whether its relationships can be imported.</summary>
public sealed record TableDetail(
    string Connection,
    TablePlace Place,
    IReadOnlyList<string> Where,
    string Sql,
    IReadOnlyList<DetailColumn> Columns,
    InsertText Code,
    bool Relationships);
