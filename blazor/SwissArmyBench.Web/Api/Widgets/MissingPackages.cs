namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>What a feature needs that this Python lacks (domain/packages.py's missing answer).</summary>
public sealed record MissingPackages
{
    public string Feature { get; init; } = string.Empty;

    public IReadOnlyList<string> Packages { get; init; } = [];

    public string Python { get; init; } = string.Empty;

    public string Command { get; init; } = string.Empty;
}
