namespace SwissArmyBench.Web.Api.Git;

/// <summary>GitHub's device flow started: the code to type and where.</summary>
public sealed record DeviceFlow
{
    public string UserCode { get; init; } = string.Empty;

    public string VerificationUri { get; init; } = string.Empty;

    public int Interval { get; init; }
}
