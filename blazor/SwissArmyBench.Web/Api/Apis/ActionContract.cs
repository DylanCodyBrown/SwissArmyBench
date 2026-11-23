namespace SwissArmyBench.Web.Api.Apis;

/// <summary>An endpoint's shape, learned (else as declared): its kind, its fields and what it maps to, the drift and
/// the renames offered.</summary>
public sealed record ActionContract(
    bool Learned,
    string Kind,
    IReadOnlyList<ActionField> Fields,
    string Drift,
    IReadOnlyList<string> Missing,
    IReadOnlyList<ActionOffer> Offers,
    string Seen,
    IReadOnlyList<string> MapsTo);
