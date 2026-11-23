using System.Text.Json;

namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A setting's name and its value (never a password's).</summary>
public sealed record NamedValue(string Name, JsonElement Value);
