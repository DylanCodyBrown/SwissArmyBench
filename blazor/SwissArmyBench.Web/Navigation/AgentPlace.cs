using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Navigation;

/// <summary>
/// Where a "navigate" notice sends the main window (the agent's app_navigate, POST /navigate; the places are
/// domain/navigation.py's): the rail's areas, Home, a connection's detail, the forms inside Connections and APIs, a
/// table's tab, a new SQL file. Back and Forward are the browser's own (<see cref="IsHistory"/>).
/// </summary>
public static class AgentPlace
{
    public const string NoticeType = "navigate";
    public const string HomeWindow = "home";
    public const string Back = "back";
    public const string Forward = "forward";

    private static readonly Dictionary<string, string> _named = new()
    {
        ["home"] = string.Empty,
        ["projects"] = "?view=projects",
        ["tables"] = "tables",
        ["structures"] = Areas.Structures.Route,
        ["blades"] = "scripts?pane=blades",
        ["new_blade"] = "scripts?pane=blades",
        ["add_connection"] = "connections?add=1",
        ["add_api"] = "apis?add=1",
        ["new_sql"] = "scripts?new=sql",
    };

    public const string WorkbenchWindow = "workbench";

    /// <summary>The notice is for the home window (every page hears it: the main window follows).</summary>
    public static bool IsForMainWindow(Notice notice) =>
        notice.Type == NoticeType && (notice.Text("window") ?? HomeWindow) == HomeWindow;

    /// <summary>The notice is for the Notebooks or Scripts page: the server told only the open one the user was
    /// last in (the page said which window it is, Layout/WindowPlace), so the page that hears it follows.</summary>
    public static bool IsForThisWorkbench(Notice notice) =>
        notice.Type == NoticeType && notice.Text("window") == WorkbenchWindow;

    public static bool IsHistory(string to) => to is Back or Forward;

    /// <summary>This app's address (under /blazor/) for the notice's place, or null when it names none.</summary>
    public static string? AddressOf(Notice notice)
    {
        var to = notice.Text("to") ?? string.Empty;
        var name = notice.Text("name");
        switch (to)
        {
            case "grid":
                return notice.Text("grid") is { Length: > 0 } grid ? $"tables?grid={Uri.EscapeDataString(grid)}" : null;
            case "connection":
                return name is { Length: > 0 } ? $"connections?name={Uri.EscapeDataString(name)}" : null;
            case "blade":
                return name is { Length: > 0 } ? $"scripts?blade={Uri.EscapeDataString(name)}" : null;
            default:
                break;
        }
        if (_named.TryGetValue(to, out var address))
        {
            return address;
        }
        return Areas.All.FirstOrDefault(a => a.Area == to || a.Route == to)?.Route;
    }
}
