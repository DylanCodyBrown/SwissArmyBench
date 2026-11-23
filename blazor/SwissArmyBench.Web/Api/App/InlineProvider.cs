namespace SwissArmyBench.Web.Api.App;

/// <summary>An inline completion provider a mode declares (an extension's INLINE_COMPLETION, GitHub Copilot's): its
/// name, the languages it completes, and its routes (complete, cancel, event, status, toggle). The pages never name a
/// provider: they call what it declares.</summary>
public sealed record InlineProvider(
    string Id,
    string Name,
    IReadOnlyList<string> Languages,
    string Complete,
    string? Cancel = null,
    string? Event = null,
    string? Status = null,
    string? Toggle = null);
