namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>GET /workbench/tables: an open table as its read-only cell's text, and where it came from.</summary>
public sealed record TableInfo(
    string Name,
    string? Grid,
    long Rows,
    string Origin,
    string? Document,
    string? Kernel,
    int Steps,
    string Code);
