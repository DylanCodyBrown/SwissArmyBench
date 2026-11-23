namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>An HTML cell's design with its names filled by the server's rules (POST /workbench/html/fill), so data
/// never becomes markup or script: the names it asks for, the ones its run did not make, and what it said.</summary>
public sealed record FilledHtml(
    string Html,
    IReadOnlyList<string> Names,
    IReadOnlyList<string> Missing,
    IReadOnlyList<string> Waiting,
    IReadOnlyList<string> Notes);
