using System.Text.Json;

namespace SwissArmyBench.Web.Api.Apis;

/// <summary>The API as read: its title, where it came from, its base address, operations, tables and sign-in.</summary>
public sealed record PlanSpec(
    string Title,
    string Source,
    string BaseUrl,
    IReadOnlyList<PlanOperation> Operations,
    IReadOnlyList<PlanTable> Tables,
    IReadOnlyDictionary<string, JsonElement> Auth);
