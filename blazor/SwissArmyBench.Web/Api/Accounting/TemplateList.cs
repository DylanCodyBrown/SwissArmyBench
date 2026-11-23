namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>POST /accounting/templates: the project's templates folder and the templates in it.</summary>
public sealed record TemplateList
{
    public string Folder { get; init; } = string.Empty;

    public IReadOnlyList<string> Templates { get; init; } = [];
}
