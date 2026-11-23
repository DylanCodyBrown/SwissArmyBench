namespace SwissArmyBench.Web.Api.Sharing;

/// <summary>Share…'s state (services/sharing.py): devtunnel installed, the sign-in, the device code, the sentence, and each app's share.</summary>
public sealed record SharingStatus
{
    public bool Installed { get; init; }

    public bool Installing { get; init; }

    public string Checks { get; init; } = string.Empty;

    public string Needs { get; init; } = string.Empty;

    public string Sentence { get; init; } = string.Empty;

    public bool SignedIn { get; init; }

    public bool WorkAccount { get; init; }

    public string? Account { get; init; }

    public bool SigningIn { get; init; }

    public DeviceCode? Device { get; init; }

    public string? SignInError { get; init; }

    public IReadOnlyList<ShareState> Shares { get; init; } = [];
}
