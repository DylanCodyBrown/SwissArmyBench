namespace SwissArmyBench.Web.Api.App;

/// <summary>A project type's mode as the backend declares it (only the parts these pages read).</summary>
public sealed record ModeInfo(
    string Type,
    string Name,
    IReadOnlyList<string> Canvases,
    string Title = "",
    string Explain = "",
    IReadOnlyList<InlineProvider>? InlineCompletion = null);
