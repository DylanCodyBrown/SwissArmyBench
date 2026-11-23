namespace SwissArmyBench.Web.Pages.Environment;

/// <summary>One thing a row does: its words, the work, whether it is the primary one, its icon.</summary>
public sealed record EnvAction(string Label, Func<Task> Run, bool Primary = false, string? Icon = null);
