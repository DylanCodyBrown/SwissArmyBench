namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>What an endpoint answers: its fields by name and type (a body's, else the answer's).</summary>
public sealed record PayloadAnswers(
    IReadOnlyDictionary<string, string>? Fields = null,
    IReadOnlyDictionary<string, string>? Body = null);
