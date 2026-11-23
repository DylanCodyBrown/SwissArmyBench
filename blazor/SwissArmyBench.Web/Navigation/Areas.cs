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
    public const string Workbook = "workbook";
    public const string Widgets = "widgets";
    public const string Session = "session";
    public const string Extensions = "extensions";

    public static readonly IReadOnlyList<RailArea> All =
    [
        new("projects", "Home", "home", "", "/workspace?open=projects", Keys: "Alt+Home"),
        new("connections", "Connections", "plug", "connections", "/workspace?open=connections"),
        new("apis", "APIs", "apis", "apis", "/workspace?open=apis"),
        new("environment", "Environment", "environment", "environment", "/workspace?open=environment"),
        new("data", "Catalog", "data", "catalog", "/workspace?open=data"),
        new("grids", "Grids", "grids", "grids", "/workspace"),
        new("erd", "ERD", "diagram", "erd", "/workspace?view=erd"),
        new("scripts", "Scripts", "code", "scripts", "/scripts?kind=script&view=list", Kind: "script"),
        new("notebooks", "Notebooks", "notebook", "notebooks", "/notebooks?kind=notebook&view=list", Kind: "notebook"),
        // The Power Apps extension's area: shown while the app's modes list the code app type.
        new(CodeApp, "Code App", "codeapp", "codeapp", "/workspace?open=codeapp"),
        // The Accounting extension's Excel canvas (the classic page has it as a Notebooks tab): shown while a mode
        // offers the excel canvas.
        new(Workbook, "Workbook", "excel", "workbook", "/notebooks?kind=notebook&view=list"),
        new(Canvas, "Canvas", "page", "canvas", "/streamlit/canvas"),
        new(Widgets, "Widgets", "sliders", "widgets", "/streamlit/widget"),
        new("analyze", "Analyze", "sandbox", "analyze", "/workspace?view=analyze"),
        new(Session, "Session", "session", "session", "/workspace?open=session"),
        new(Extensions, "Extensions", "extensions", "extensions", "/workspace?open=extensions"),
        new("settings", "Settings", "cog", "settings", "/workspace?open=settings"),
    ];

    /// <summary>The structures viewer (off the rail: the Environment's rows open into it), marked as Environment.</summary>
    public static readonly RailArea Structures = new("structures", "Structures", "structures", "structures", "/workspace?open=structures");

    /// <summary>The area an address of this app belongs to (its first part), for the rail's mark.</summary>
    public static string? AreaOfPath(string relativePath)
    {
        var first = relativePath.Split('?', '#')[0].Split('/')[0];
        if (first == Structures.Route)
        {
            return "environment";
        }
        return All.FirstOrDefault(a => a.Route == first)?.Area ?? (first.StartsWith("x-", StringComparison.Ordinal) ? first[2..] : null);
    }
}
