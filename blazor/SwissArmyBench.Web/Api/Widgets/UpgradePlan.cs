namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>Upgrade to In/Out's preview: the diff, the session state keys made declarations, what is kept.</summary>
public sealed record UpgradePlan
{
    public string Diff { get; init; } = string.Empty;

    public IReadOnlyList<UpgradeChange> Changes { get; init; } = [];

    public IReadOnlyList<string> Kept { get; init; } = [];
}
