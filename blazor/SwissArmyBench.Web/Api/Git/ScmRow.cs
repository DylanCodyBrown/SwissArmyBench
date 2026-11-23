namespace SwissArmyBench.Web.Api.Git;

/// <summary>One commit of the history.</summary>
public sealed record ScmRow
{
    public string Id { get; init; } = string.Empty;

    public IReadOnlyList<string> Parents { get; init; } = [];

    public string Subject { get; init; } = string.Empty;

    public string Message { get; init; } = string.Empty;

    public string Author { get; init; } = string.Empty;

    public string Email { get; init; } = string.Empty;

    public string Date { get; init; } = string.Empty;
}
