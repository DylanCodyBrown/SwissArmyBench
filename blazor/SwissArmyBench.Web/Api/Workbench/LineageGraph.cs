namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>POST /workbench/lineage: a cell's lineage back to the data: the nodes in flow order, the Mermaid text,
/// notes, and each node's value summarised (a table's size and first rows, a value, a picture).</summary>
public sealed record LineageGraph(
    string Target,
    IReadOnlyList<LineageNode> Nodes,
    IReadOnlyList<string> Notes,
    string Mermaid,
    IReadOnlyDictionary<string, LineageValue>? Values,
    bool Busy,
    string? Mark);
