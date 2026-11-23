namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>Who is signed in to the Power Platform.</summary>
public sealed record CodeAppAccount
{
    public bool SignedIn { get; init; }

    public string? Active { get; init; }
}
