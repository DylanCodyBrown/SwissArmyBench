using System.Text.Json;

namespace SwissArmyBench.Web.Api.Apis;

/// <summary>POST /apis/try: an operation's first rows, written nowhere.</summary>
public sealed record TriedOperation(
    string Table,
    IReadOnlyList<string> Columns,
    IReadOnlyList<IReadOnlyList<JsonElement>> Rows);
