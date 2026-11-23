namespace SwissArmyBench.Web.Api.Connections;

/// <summary>What a connection kind writes (its operations and Write starters), or why it is read-only, in words.</summary>
public sealed record WritesInfo(
    bool Writable,
    string Words = "",
    string Reason = "",
    IReadOnlyList<string>? Operations = null,
    IReadOnlyList<string>? Starters = null,
    string How = "",
    string Note = "");
