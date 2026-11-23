using System.Text.Json;

using SwissArmyBench.Web.Api.Canvas;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>
/// The wiring's words and marks on the page (the classic canvasWiring.ts): everything comes from the canvas's state
/// (services/canvas.py); the page never decides a rule, it says what the server's answer holds.
/// </summary>
public static class WiringRules
{
    public const string Viewer = "app.viewer";

    private static readonly IReadOnlyDictionary<string, string> _viewerWords = new Dictionary<string, string>
    {
        ["app.viewer_email"] = "email",
        ["app.viewer_id"] = "account id",
        ["app.viewer_roles"] = "roles",
    };

    public static bool IsApp(string reference) => reference == Viewer || reference.StartsWith("app.viewer_", StringComparison.Ordinal);

    public static string ViewerWord(string reference) => _viewerWords.GetValueOrDefault(reference, reference);

    /// <summary>Whether an Out of type <paramref name="given"/> can feed an In of type <paramref name="wanted"/>
    /// (widget_contract.fits).</summary>
    public static bool Fits(string given, string wanted) =>
        given == wanted
        || (wanted == "float" && given == "int")
        || (wanted == "Table" && given is "list[dict]" or "list")
        || (wanted == "list" && given.StartsWith("list", StringComparison.Ordinal))
        || (wanted.StartsWith("list[", StringComparison.Ordinal) && given == "list")
        || (wanted == "list[float]" && given == "list[int]");

    /// <summary>An Out in words: "w3 sales_filter · region"; one from another page "Reports · w3 sales_filter.region";
    /// the app's own "The viewer".</summary>
    public static string OutWords(string reference, CanvasWiring wiring, string page, IReadOnlyDictionary<string, string> names)
    {
        if (reference == Viewer)
        {
            return "The viewer (who is viewing)";
        }
        if (reference.StartsWith("app.viewer_", StringComparison.Ordinal))
        {
            return $"The viewer's {ViewerWord(reference)}";
        }
        if (!wiring.Outs.TryGetValue(reference, out var o))
        {
            return reference;
        }
        if (!string.IsNullOrEmpty(o.Page) && o.Page != page)
        {
            return $"{names.GetValueOrDefault(o.Page, o.Page)} · {o.Instance} {o.Widget}.{o.Port}";
        }
        return $"{o.Instance} {o.Widget} · {o.Port}";
    }

    /// <summary>A wire's key in a picker: "table:orders", "out:w1.region", or its kind for a value, a page value or
    /// a list of tables.</summary>
    public static string KeyOf(JsonElement? wire)
    {
        if (wire is not { ValueKind: JsonValueKind.Object } given)
        {
            return string.Empty;
        }
        var first = given.EnumerateObject().FirstOrDefault();
        if (first.Name is null)
        {
            return string.Empty;
        }
        return first.Name is "value" or "page" or "tables"
            ? first.Name
            : $"{first.Name}:{(first.Value.ValueKind == JsonValueKind.String ? first.Value.GetString() : first.Value.GetRawText())}";
    }

    /// <summary>A picker's choice as the wire it sends ("table:orders" is {table: "orders"}); null: not wired.</summary>
    public static Dictionary<string, object?>? WireOf(string picked)
    {
        var at = picked.IndexOf(':', StringComparison.Ordinal);
        return at < 0 ? null : new Dictionary<string, object?> { [picked[..at]] = picked[(at + 1)..] };
    }

    /// <summary>A node's marks: lit as the selected widget's source or reader, or broken (either end).</summary>
    public static string NodeMarks(string id, IReadOnlyCollection<string> selected, CanvasWiring? wiring)
    {
        if (wiring is null)
        {
            return string.Empty;
        }
        static string Mine(string reference) => reference.Split('.')[0];
        var marks = new List<string>();
        if (selected.Any(s => wiring.Wires.Any(w => Mine(w.To) == s && Mine(w.From) == id)))
        {
            marks.Add("wire-source");
        }
        if (selected.Any(s => wiring.Wires.Any(w => Mine(w.From) == s && Mine(w.To) == id)))
        {
            marks.Add("wire-reader");
        }
        if (wiring.Broken.Any(b => b.Instance == id || (b.Source is { } source && Mine(source) == id)))
        {
            marks.Add("wire-broken");
        }
        return string.Concat(marks.Select(m => $" {m}"));
    }

    /// <summary>Before Play: the broken wires, one line each (empty when none is broken).</summary>
    public static string BrokenWords(CanvasWiring? wiring)
    {
        var broken = wiring?.Broken ?? [];
        if (broken.Count == 0)
        {
            return string.Empty;
        }
        var head = broken.Count == 1 ? "A wire is" : $"{broken.Count} wires are";
        return $"{head} broken: {string.Join(' ', broken.Select(b => $"{b.Instance}.{b.Port}: {b.Reason}"))}";
    }
}
