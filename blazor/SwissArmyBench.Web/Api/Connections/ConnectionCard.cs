namespace SwissArmyBench.Web.Api.Connections;

/// <summary>One card of the Connections page (GET /connections/usage): its type, its status word (a cheap check, never a run) and its calls.</summary>
public sealed record ConnectionCard(string Name, string Connection, string Type, string? Template = null, string? Dialect = null, string Description = "", string Status = "ready", IReadOnlyList<string>? Missing = null, string Error = "", bool CatalogLoaded = false, CallsInfo? Calls = null, string TablesKind = "", IReadOnlyList<LocalNote>? Local = null, WritesInfo? Writes = null, string? Colour = null, string? Words = null, int? Tables = null);
