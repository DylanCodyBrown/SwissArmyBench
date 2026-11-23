namespace SwissArmyBench.Web.Pages.Scm;

/// <summary>A quick pick asked (VS Code's): its placeholder, its lines, whether typed words may be the answer, and
/// the answer it waits for (null: Escape).</summary>
public sealed record QuickPickRequest(
    string Placeholder,
    IReadOnlyList<PickChoice> Items,
    bool Free,
    TaskCompletionSource<string?> Answer);
