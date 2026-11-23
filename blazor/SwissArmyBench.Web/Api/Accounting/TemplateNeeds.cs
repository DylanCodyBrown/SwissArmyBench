namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>The columns a template's bindings read: the groups' and the lines'.</summary>
public sealed record TemplateNeeds
{
    public IReadOnlyList<string> Data { get; init; } = [];

    public IReadOnlyList<string> Lines { get; init; } = [];
}
