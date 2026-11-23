namespace SwissArmyBench.Web.Api.Environment;

/// <summary>GET /environment: every row (or the ones a search found), each tab's count, the project's Python and the project, the tables' memory, whether the package index was asked.</summary>
public sealed record EnvironmentAnswer(
    IReadOnlyList<EnvironmentItem> Items,
    IReadOnlyDictionary<string, int> Counts,
    IReadOnlyList<EnvironmentTab> Tabs,
    EnvironmentPython? Python = null,
    string Memory = "",
    EnvironmentProject? Project = null,
    bool Checked = false);
