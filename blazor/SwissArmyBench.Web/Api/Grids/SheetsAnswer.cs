namespace SwissArmyBench.Web.Api.Grids;

/// <summary>POST /files/sheets: a workbook's sheets, in order.</summary>
public sealed record SheetsAnswer(IReadOnlyList<string> Sheets);
