namespace SwissArmyBench.Web.Pages.Scm;

/// <summary>VS Code's modal dialog asked: its message, detail and buttons (the first the primary; Cancel is added),
/// and the button it waits for (null: Cancel or Escape).</summary>
public sealed record DialogRequest(
    string Message,
    string Detail,
    IReadOnlyList<string> Buttons,
    TaskCompletionSource<string?> Answer);
