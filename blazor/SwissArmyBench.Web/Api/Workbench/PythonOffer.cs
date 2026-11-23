namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A notebook's older environment, offered to the project: its libraries and its one line.</summary>
public sealed record PythonOffer(string Document, IReadOnlyList<string> Libraries, string Words);
