namespace SwissArmyBench.Web.Api.Connections;

/// <summary>GET /connections/{name}/tree: its tables as a tree.</summary>
public sealed record ConnectionTree(string Connection, string Kind, IReadOnlyList<TreeGroup> Groups);
