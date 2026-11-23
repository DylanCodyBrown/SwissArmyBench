namespace SwissArmyBench.Web.Api.Environment;

/// <summary>A notebook's older environment: its libraries the project's Python may take, in one line.</summary>
public sealed record PythonOffer(string Document, IReadOnlyList<string> Libraries, string Words);
