namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>One widget's use of an endpoint (or one of its Events): its canvas and page, what it expects, what it gets, each mismatch.</summary>
public sealed record PayloadUse(
    string Canvas,
    string Page,
    string Widget,
    string Endpoint,
    string Expects,
    PayloadAnswers Answers,
    IReadOnlyList<string> Problems,
    string? Event = null);
