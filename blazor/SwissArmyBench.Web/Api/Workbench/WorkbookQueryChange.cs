namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>One workbook query in a save or its preview: changed, added, kept (never removed from the workbook) or
/// same, with the sentence that says what Excel does with it.</summary>
public sealed record WorkbookQueryChange(string Query, string What, string Words);
