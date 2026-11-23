using System.Text.Json;

namespace SwissArmyBench.Web.Api.Apis;

/// <summary>POST /apis/{name}/calls/{operation}/write: a dry run (the table's columns, the mapping matched by name,
/// the rows and calls, the first requests, what is still to map) or the write's counts and its results opened in
/// Structures.</summary>
public sealed record WriteRowsAnswer(
    IReadOnlyList<string>? Columns = null,
    IReadOnlyDictionary<string, JsonElement>? Mapping = null,
    IReadOnlyList<string>? Missing = null,
    bool DryRun = false,
    int Rows = 0,
    int Calls = 0,
    IReadOnlyList<JsonElement>? First = null,
    int Written = 0,
    int Failed = 0,
    string? Structure = null);
