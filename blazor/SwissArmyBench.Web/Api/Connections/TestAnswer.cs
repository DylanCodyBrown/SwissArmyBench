namespace SwissArmyBench.Web.Api.Connections;

/// <summary>POST /connections/test and /blades/{name}/test: what the code made, when it worked (a Python connection's tables and columns), and a file's or table's first rows.</summary>
public sealed record TestAnswer(
    string? Type = null,
    string? Found = null,
    string? Name = null,
    string? PreviewError = null,
    IReadOnlyList<string>? Variables = null,
    TablePreview? Preview = null,
    int? Tables = null,
    int? Columns = null);
