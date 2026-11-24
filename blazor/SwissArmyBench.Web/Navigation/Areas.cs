namespace SwissArmyBench.Web.Navigation;

/// <summary>
/// The rail's areas in the order of the work (the classic rail.ts AREAS; domain/navigation.py holds the same): where
/// the data comes from, getting and shaping it, building, presenting, then the log. Extensions and Settings sit at
/// the bottom. Canvas and Widgets show only while a mode offers the Streamlit canvas; an extension's own areas
/// (GET /app/areas) go before Session.
/// </summary>
public static class Areas
{
    public const string Canvas = "canvas";
    public const string CodeApp = "codeapp";
    public const string Widgets = "widgets";
    public const string Session = "session";
    public const string Extensions = "extensions";

    /// <summary>The Tables page's old address (Grids, renamed 2026-11-23): it still lands there, marked as Tables.</summary>
    public const string OldTablesRoute = "grids";

    public static readonly IReadOnlyList<RailArea> All =
    [
        new("projects", "Home", "home", "", Keys: "Alt+Home"),
        new("connections", "Connections", "plug", "connections"),
        new("apis", "APIs", "apis", "apis"),
        new("environment", "Environment", "environment", "environment"),
        new("data", "Catalog", "data", "catalog"),
        new("grids", "Tables", "grids", "tables"),
        new("erd", "ERD", "diagram", "erd"),
        new("scripts", "Scripts", "code", "scripts", Kind: "script"),
        new("notebooks", "Notebooks", "notebook", "notebooks", Kind: "notebook"),
        // The Power Apps extension's area: shown while the app's modes list the code app type.
        new(CodeApp, "Code App", "codeapp", "codeapp"),
        new(Canvas, "Canvas", "page", "canvas"),
        new(Widgets, "Widgets", "sliders", "widgets"),
        new("analyze", "Analyze", "sandbox", "analyze"),
        new(Session, "Session", "session", "session"),
        new(Extensions, "Extensions", "extensions", "extensions"),
        new("settings", "Settings", "cog", "settings"),
    ];

    /// <summary>The structures viewer (off the rail: the Environment's rows open into it), marked as Environment.</summary>
    public static readonly RailArea Structures = new("structures", "Structures", "structures", "structures");

    /// <summary>The area an address of this app belongs to (its first part), for the rail's mark.</summary>
    public static string? AreaOfPath(string relativePath)
    {
        var first = relativePath.Split('?', '#')[0].Split('/')[0];
        if (first == OldTablesRoute)
        {
            return "grids";
        }
        if (first == Structures.Route)
        {
            return "environment";
        }
        return All.FirstOrDefault(a => a.Route == first)?.Area ?? (first.StartsWith("x-", StringComparison.Ordinal) ? first[2..] : null);
    }
}
