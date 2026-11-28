namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>Reload (POST /scripts/pq/workbook/reload): the workbook's queries read again into the linked file.</summary>
public sealed record WorkbookReload(string Path, string Text, string Workbook);
