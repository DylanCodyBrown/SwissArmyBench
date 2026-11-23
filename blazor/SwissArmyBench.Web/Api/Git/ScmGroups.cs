using System.Text.Json.Serialization;

namespace SwissArmyBench.Web.Api.Git;

/// <summary>VS Code's three groups: Merge Changes, Staged Changes and Changes.</summary>
public sealed record ScmGroups
{
    public IReadOnlyList<ScmResource> Merge { get; init; } = [];

    public IReadOnlyList<ScmResource> Index { get; init; } = [];

    // The server writes this one in VS Code's own camelCase.
    [JsonPropertyName("workingTree")]
    public IReadOnlyList<ScmResource> WorkingTree { get; init; } = [];
}
