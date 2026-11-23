namespace SwissArmyBench.Web.Api.Grids;

/// <summary>One likely join: a column here, one there, how many values they share and the relationship it reads as.</summary>
public sealed record KeyPair(
    string SourceColumn,
    string TargetColumn,
    string TargetGrid,
    string TargetDataset,
    long Shared,
    double SourceFound,
    double TargetFound,
    string Relationship,
    double Score);
