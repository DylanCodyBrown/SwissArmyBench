namespace SwissArmyBench.Web.Api.Catalog;

/// <summary>The Catalog's tree with nothing typed (GET /explorer/browse): each connection with its tables by database
/// and schema, then the sections (the open tables, the sandbox, Structures, the APIs' tables, the blades).</summary>
public sealed record BrowseAnswer(IReadOnlyList<BrowseConnection> Connections, IReadOnlyList<BrowseSection> Sections);
