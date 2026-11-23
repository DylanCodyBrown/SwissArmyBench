namespace SwissArmyBench.Web.Api.Apis;

/// <summary>POST /apis/{name}/calls/{operation}: the call's status and time, the server's words, and its answer
/// opened in Structures (its id).</summary>
public sealed record ApiCallAnswer(
    int Status,
    double Ms,
    string? Said,
    string? Structure,
    string? Name,
    SuggestedTable? SuggestTable = null);
