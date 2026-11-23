namespace SwissArmyBench.Web.Pages.Scm;

/// <summary>A line of VS Code's context menu (the classic scmPage.ts MenuItem): its words, what it does, greyed out
/// (what needs a local Git), its submenu, its keys, its tick. Null in a list is a separator.</summary>
public sealed record ScmMenuItem(
    string Label,
    Func<Task>? Run = null,
    bool Disabled = false,
    IReadOnlyList<ScmMenuItem?>? Submenu = null,
    string? Keys = null,
    bool? Checked = null)
{
    /// <summary>A command VS Code has that needs a local Git: shown, greyed out.</summary>
    public static ScmMenuItem Off(string label) => new(label, Disabled: true);
}
