namespace SwissArmyBench.Web.Api.Apis;

/// <summary>One API's actions and since when its Discover is allowed (none: not).</summary>
public sealed record ActionApi(string Api, IReadOnlyList<ActionLearned> Actions, string? AllowedSince = null);
