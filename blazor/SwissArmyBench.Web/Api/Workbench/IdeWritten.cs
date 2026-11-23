namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>An applied rename's or replace's answer: the files written.</summary>
public sealed record IdeWritten(IReadOnlyList<string> Written);
