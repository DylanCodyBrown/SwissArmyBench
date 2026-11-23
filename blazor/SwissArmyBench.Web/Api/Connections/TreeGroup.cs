namespace SwissArmyBench.Web.Api.Connections;

/// <summary>One schema's (or a Power BI dataset's) tables in a connection's tree.</summary>
public sealed record TreeGroup(
    IReadOnlyList<TreeTable> Tables,
    string? Database = null,
    string? Schema = null,
    string? Dataset = null,
    int Count = 0);
