namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>An imported workbook as a template: its file, its places bound, its preview, what it needs.</summary>
public sealed record WorkbookTemplate
{
    public string Name { get; init; } = string.Empty;

    public string Folder { get; init; } = string.Empty;

    public string Path { get; init; } = string.Empty;

    public IReadOnlyList<TemplateBinding> Bindings { get; init; } = [];

    public WorkbookPreview Preview { get; init; } = new();

    public TemplateNeeds Needs { get; init; } = new();
}
