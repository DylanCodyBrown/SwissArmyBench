namespace SwissArmyBench.Web.Pages.Home;

/// <summary>One count on a project's card: how many, of what (in the singular) and its icon.</summary>
public sealed record CardCount(int Count, string Word, string Icon)
{
    /// <summary>"4 tables", "1 app".</summary>
    public string Words => $"{Count:N0} {Word}{(Count == 1 ? string.Empty : "s")}";
}
