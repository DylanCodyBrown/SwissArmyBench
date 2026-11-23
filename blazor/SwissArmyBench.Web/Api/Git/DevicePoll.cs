namespace SwissArmyBench.Web.Api.Git;

/// <summary>The device flow asked again: pending, signed in, or its words.</summary>
public sealed record DevicePoll
{
    public string State { get; init; } = string.Empty;

    public int? Interval { get; init; }

    public string? Words { get; init; }
}
