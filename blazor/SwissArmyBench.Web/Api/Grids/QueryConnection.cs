namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A connection as GET /connections lists it: its name, what it is (database, file, python...), its kind in
/// words, how its tables are read, and a password with no source on this computer.</summary>
public sealed record QueryConnection(
    string Name,
    string Connection,
    string? Type = null,
    string? TablesKind = null,
    PasswordNeed? NeedsPassword = null)
{
    /// <summary>A query runs on it in its own SQL (Dataverse's Web API side does not).</summary>
    public bool RunsSql => Connection == "database" && TablesKind != "dataverse_web";

    public bool Dax => TablesKind == "powerbi";

    public string KindWords => Type is { Length: > 0 } type ? type : Dax ? "Power BI workspace" : "Database";
}
