namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>One line of a Canvas menu (the classic canvasMenus.ts MenuEntry): its words, its key shown at the right,
/// a line above it (a group's start), what it does or the widget picker it opens beside it, ticked, greyed out.</summary>
public sealed record CanvasMenuItem(
    string Label,
    Func<Task>? Run = null,
    string? Key = null,
    bool Group = false,
    bool? Checked = null,
    bool Disabled = false,
    Func<string, Task>? Pick = null);
