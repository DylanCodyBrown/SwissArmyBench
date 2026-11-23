namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A rename's or a replace's plan: each file's changed lines, the files left alone and why, each file's
/// new text (a rename's), and how many replacements (a replace's).</summary>
public sealed record IdePlan(
    IReadOnlyList<IdeFilePreview> Preview,
    IReadOnlyList<IdeSkipped> Skipped,
    IReadOnlyDictionary<string, string>? Changes = null,
    int Count = 0);
