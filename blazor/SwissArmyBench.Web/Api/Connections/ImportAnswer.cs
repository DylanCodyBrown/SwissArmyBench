using System.Text.Json;

namespace SwissArmyBench.Web.Api.Connections;

/// <summary>POST /connections/found/import: the connections made, the variables declared for their passwords, the ones skipped.</summary>
public sealed record ImportAnswer(
    IReadOnlyList<ImportedConnection> Imported,
    IReadOnlyList<SkippedRow> Skipped,
    JsonElement Variables);
