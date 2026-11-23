namespace SwissArmyBench.Web.Api.Connections;

/// <summary>One connection another project offers.</summary>
public sealed record OfferedConnection(string Name, string Description = "");
