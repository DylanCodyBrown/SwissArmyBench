using SwissArmyBench.Web.Api.Canvas;
using SwissArmyBench.Web.Api.Widgets;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>What an In's source picker offers (the classic canvasWiring.ts tableOptions and outOptions): the tables
/// (the Sandbox first), the Outs that fit (this page's "Page values", each other page's by its name, the app's own),
/// the GET endpoints, the variables. Every rule is the server's: the Outs and their types come from the state.</summary>
public static class SourceOptions
{
    private static readonly string[] _scalars = ["str", "int", "float", "bool", "date", "datetime"];

    public static IReadOnlyList<PickGroup> Tables(WidgetContext? context)
    {
        if (context is null)
        {
            return [];
        }
        var connections = context.ConnectionTables
            .OrderByDescending(c => c.Key == "Sandbox")
            .ThenBy(c => c.Key, StringComparer.Ordinal)
            .Select(c => (c.Key, (IReadOnlyList<string>)(c.Value ?? [])));
        return new[] { ("Open tables", context.OpenTables), ("data.ipynb", context.DataTables) }
            .Concat(connections)
            .Where(g => g.Item2.Count > 0)
            .Select(g => new PickGroup(g.Item1, g.Item2.Select(n => new PickOption($"table:{n}", n)).ToList()))
            .ToList();
    }

    /// <summary>The Outs an In of <paramref name="port"/>'s type can read (tablesOnly: a list of tables' entry).</summary>
    public static IReadOnlyList<PickGroup> Outs(WidgetPort port, string id, string page, CanvasWiring wiring, bool tablesOnly, IReadOnlyDictionary<string, string> names)
    {
        var wanted = tablesOnly ? "Table" : port.Type;
        var refs = wiring.Outs.Where(o => o.Value.Instance != id && WiringRules.Fits(o.Value.Type, wanted)).ToList();
        string PageOf(OutRef o) => !string.IsNullOrEmpty(o.Page) ? o.Page : wiring.Ports.GetValueOrDefault(o.Instance)?.Page ?? string.Empty;
        PickOption Option(KeyValuePair<string, OutRef> o) => new($"out:{o.Key}", Words(o.Key, o.Value));
        var widgets = refs.Where(o => !WiringRules.IsApp(o.Key)).ToList();
        var here = widgets.Where(o => PageOf(o.Value) == page).Select(Option).ToList();
        var others = widgets
            .Where(o => PageOf(o.Value) != page)
            .GroupBy(o => PageOf(o.Value))
            .Select(g => new PickGroup($"{names.GetValueOrDefault(g.Key, g.Key)} (another page)", g.Select(Option).ToList(), g.Key));
        var app = refs.Where(o => WiringRules.IsApp(o.Key)).Select(Option).ToList();
        return new[] { new PickGroup("Page values", here) }
            .Concat(others)
            .Append(new PickGroup("The app", app))
            .Where(g => g.Options.Count > 0)
            .ToList();
    }

    /// <summary>The GET endpoints, by their API, for an In that takes a table, a dict or a list.</summary>
    public static IReadOnlyList<PickGroup> Endpoints(WidgetPort port, WidgetContext? context)
    {
        var gets = (context?.Endpoints ?? []).Where(ApiActions.ReadsOnly).ToList();
        if (gets.Count == 0 || !(port.Type is "Table" or "dict" || port.Type.StartsWith("list", StringComparison.Ordinal)))
        {
            return [];
        }
        return ApiActions.Groups(gets)
            .Select(g => new PickGroup(g.Key, g.Select(r => new PickOption($"endpoint:{r}", ApiActions.Parts(r).Words)).ToList()))
            .ToList();
    }

    public static IReadOnlyList<PickGroup> Variables(WidgetPort port, WidgetContext? context) =>
        context is { Variables.Count: > 0 } && _scalars.Contains(port.Type)
            ? [new PickGroup("Variables", context.Variables.Select(v => new PickOption($"variable:{v}", v)).ToList())]
            : [];

    private static string Words(string reference, OutRef o)
    {
        if (reference == WiringRules.Viewer)
        {
            return "viewer: who is viewing";
        }
        if (WiringRules.IsApp(reference))
        {
            return $"{o.Port}: the viewer's {WiringRules.ViewerWord(reference)}";
        }
        return $"{o.Instance} {o.Widget} · {o.Port} ({(o.Direction == "event" ? "its last payload" : o.Type)})";
    }
}
