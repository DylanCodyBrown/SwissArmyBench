namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A column in the data dictionary: its plain type, description, and where it comes from.</summary>
public sealed record DictionaryColumn(string Name, string Type, string Description, string ComesFrom);
