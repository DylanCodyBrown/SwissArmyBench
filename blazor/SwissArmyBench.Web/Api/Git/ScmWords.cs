namespace SwissArmyBench.Web.Api.Git;

/// <summary>An action's answer in words (pull, push, sync, checkout, commit, connect).</summary>
public sealed record ScmWords
{
    public string Words { get; init; } = string.Empty;

    public int Pushed { get; init; }

    public int Files { get; init; }
}
