using System.Text.Json;

namespace SwissArmyBench.Web.Api.Connections;

/// <summary>Where a query came from: a kernel's document and cell.</summary>
public sealed record QuerySource(string? Kernel = null, string? Document = null, JsonElement? Cell = null);
