namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>The built workbook read back (files.py preview): its sheets and named ranges.</summary>
public sealed record WorkbookPreview
{
    public IReadOnlyList<PreviewSheet> Sheets { get; init; } = [];

    public IReadOnlyDictionary<string, string> Names { get; init; } = new Dictionary<string, string>();
}
