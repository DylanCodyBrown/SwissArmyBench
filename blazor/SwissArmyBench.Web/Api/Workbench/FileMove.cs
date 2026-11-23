namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A module's or a package's rename (POST /scripts/files/move): the plan (its imports' preview, the files
/// left alone, the module's old and new names), or once applied, where it went.</summary>
public sealed record FileMove(
    IReadOnlyList<IdeFilePreview>? Preview = null,
    IReadOnlyList<IdeSkipped>? Skipped = null,
    string? Module = null,
    string? NewModule = null,
    string? To = null);
