namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>A group of a source picker (an optgroup: null label for loose options), and the page it is (another
/// page's Outs).</summary>
public sealed record PickGroup(string? Label, IReadOnlyList<PickOption> Options, string? Page = null);
