using System.Text.Json;

namespace SwissArmyBench.Web.Api.Connections;

/// <summary>POST /project/import: the ones skipped (the library has one by that name) and those that need a password here.</summary>
public sealed record ImportDone(
    IReadOnlyList<string> Skipped,
    IReadOnlyDictionary<string, JsonElement> NeedsPassword);
