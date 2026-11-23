namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>POST /workbench/tables/arrange for a script: its text with its `# region Tables` in place.</summary>
public sealed record ArrangedScript(string Text);
