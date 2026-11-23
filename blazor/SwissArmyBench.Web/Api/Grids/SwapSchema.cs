namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A schema of the other connection's catalog: its database and name, and how many tables it holds.</summary>
public sealed record SwapSchema(string Database, string Schema, int Tables);
