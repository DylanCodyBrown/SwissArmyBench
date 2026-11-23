namespace SwissArmyBench.Web.Pages.Environment;

/// <summary>One column of an Environment tab: its heading and its width in the list's grid.</summary>
public sealed record EnvColumn(string Head, string Width)
{
    /// <summary>Each tab's columns, in the classic order and widths.</summary>
    public static readonly IReadOnlyDictionary<string, IReadOnlyList<EnvColumn>> Of = new Dictionary<string, IReadOnlyList<EnvColumn>>
    {
        ["table"] = [new("Rows by columns", "130px"), new("Columns", "minmax(160px,2fr)"), new("Grids", "110px"), new("Used in", "110px"), new("From", "minmax(130px,1fr)")],
        ["variable"] = [new("Type", "110px"), new("Value", "minmax(200px,2.4fr)"), new("Used in", "110px"), new("From", "minmax(130px,1fr)")],
        ["structure"] = [new("Format", "110px"), new("Size", "130px"), new("Paths", "minmax(180px,2fr)"), new("Used in", "110px"), new("File", "minmax(150px,1fr)")],
        ["setting"] = [new("Kind", "80px"), new("Value", "minmax(160px,1.4fr)"), new("Comes from", "minmax(180px,1.6fr)"), new("Used in", "110px")],
        ["library"] = [new("Pinned", "86px"), new("Version", "170px"), new("What it is for", "minmax(140px,1.4fr)"), new("Imported in", "110px")],
    };
}
