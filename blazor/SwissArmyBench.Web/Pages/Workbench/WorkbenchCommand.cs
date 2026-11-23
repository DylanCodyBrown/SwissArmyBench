namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>One command of the page's palette (the classic workbenchCommandList.ts entry): its group (File, Run,
/// Cell, View...), its words, its keys, what it does, and why it cannot now when it is greyed out.</summary>
public sealed record WorkbenchCommand(
    string Id,
    string Group,
    string Label,
    Func<Task> Run,
    string? Keys = null,
    string? Disabled = null);
