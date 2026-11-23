namespace SwissArmyBench.Web.Api.Extensions;

/// <summary>What a folder extension needs that this Python lacks: the packages and the command.</summary>
public sealed record MissingNeed(
    IReadOnlyList<string> Packages,
    string Command = "",
    string Feature = "",
    string Python = "app");
