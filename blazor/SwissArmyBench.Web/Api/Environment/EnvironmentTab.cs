namespace SwissArmyBench.Web.Api.Environment;

/// <summary>One tab of the Environment: its kind (table, variable, structure, setting, library), its name and its columns' headings.</summary>
public sealed record EnvironmentTab(string Kind, string Name, IReadOnlyList<string> Columns);
