namespace SwissArmyBench.Web.Api.Grids;

/// <summary>GET /connections/{name}/references: the code that names a connection.</summary>
public sealed record ReferencesAnswer(IReadOnlyList<CodeReference> References);
