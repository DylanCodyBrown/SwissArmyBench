namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>POST /projects/dictionary's answer.</summary>
public sealed record DictionaryTables(IReadOnlyList<DictionaryTable> Tables);
