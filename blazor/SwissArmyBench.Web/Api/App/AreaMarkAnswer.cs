namespace SwissArmyBench.Web.Api.App;

/// <summary>An area's mark route's answer: a mark, or null (up to date, not connected, no project).</summary>
public sealed record AreaMarkAnswer(AreaMark? Mark);
