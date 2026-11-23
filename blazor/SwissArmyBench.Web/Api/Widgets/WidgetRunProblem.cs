namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>Why a widget's run, or a canvas's Play or Launch, did not start (server/live_runs.py): "missing" (the
/// Python lacks Streamlit: what, which Python, the command and where Install puts them) or "failed" (its words).</summary>
public sealed record WidgetRunProblem
{
    /// <summary>The problem's kind that names missing packages.</summary>
    public const string MissingKind = "missing";

    public string Kind { get; init; } = string.Empty;

    public string? Message { get; init; }

    public string? Feature { get; init; }

    public IReadOnlyList<string> Packages { get; init; } = [];

    public string? Python { get; init; }

    public string? Command { get; init; }

    /// <summary>Where Install puts them: "project" (the open project's Python) or "app" (the app's own).</summary>
    public string? Install { get; init; }

    /// <summary>The packages as the one install prompt takes them, or null when nothing is missing.</summary>
    public MissingPackages? Missing => Kind == MissingKind && Packages.Count > 0
        ? new MissingPackages(Feature ?? "Streamlit widgets", Packages, Python ?? MissingPackages.AppPython, Command ?? string.Empty)
        : null;
}
