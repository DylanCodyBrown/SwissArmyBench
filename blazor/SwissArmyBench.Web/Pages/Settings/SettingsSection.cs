namespace SwissArmyBench.Web.Pages.Settings;

/// <summary>One box of the Settings page as its section list names it: its id (the box's data-section), its title
/// and its icon (the box's own legend's).</summary>
public sealed record SettingsSection(string Id, string Title, string Icon)
{
    public const string Theme = "theme";
    public const string Team = "team";
    public const string Collaboration = "collaboration";
    public const string Project = "project";
    public const string Session = "session";
    public const string Updates = "updates";
    public const string Claude = "claude";
    public const string Beta = "beta";
    public const string Agent = "agent";

    /// <summary>Every section in the page's order: Theme first, the Team box right after it.</summary>
    public static IReadOnlyList<SettingsSection> All { get; } =
    [
        new(Theme, "Theme", "sun"),
        new(Team, "Team", "user"),
        new(Collaboration, "Collaboration", "chat"),
        new(Project, "This project", "project"),
        new(Session, "Session", "session"),
        new(Updates, "Updates", "export"),
        new(Claude, "Claude", "claude"),
        new(Beta, "Beta", "edit"),
        new(Agent, "Connect an agent", "agent"),
    ];
}
