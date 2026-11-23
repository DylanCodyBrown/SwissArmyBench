namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A setting's part of the form (where, who, security) and its rank there.</summary>
public sealed record FieldPlace(string Part, int Rank);
