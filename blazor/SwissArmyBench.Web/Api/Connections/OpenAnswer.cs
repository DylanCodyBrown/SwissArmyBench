namespace SwissArmyBench.Web.Api.Connections;

/// <summary>POST /connections/{name}/open: the table open as a grid, or a workbook's sheets to choose from.</summary>
public sealed record OpenAnswer(string? Dataset = null, IReadOnlyList<string>? Sheets = null);
