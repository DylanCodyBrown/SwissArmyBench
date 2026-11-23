namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>A relationship the finder suggests, with its evidence in plain words.</summary>
public sealed record Suggestion(
    string From,
    IReadOnlyList<string> FromColumns,
    string To,
    IReadOnlyList<string> ToColumns,
    string Kind,
    double Confidence,
    IReadOnlyList<string> Reasons,
    bool Known = false);
