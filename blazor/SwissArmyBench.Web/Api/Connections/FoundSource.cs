namespace SwissArmyBench.Web.Api.Connections;

/// <summary>Where a found connection was read: the tool and its file.</summary>
public sealed record FoundSource(string Tool, string Where);
