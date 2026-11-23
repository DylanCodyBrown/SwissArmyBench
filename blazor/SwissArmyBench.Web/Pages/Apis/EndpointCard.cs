using System.Text.RegularExpressions;

namespace SwissArmyBench.Web.Pages.Apis;

/// <summary>One endpoint card of Add API's form (the classic addApi.ts endpoint): its method, path, parameters (each
/// one's Needed tick; a path's {word} always needed), Read as a table and the columns to keep. A form's own state,
/// changed as the user types.</summary>
public sealed partial class EndpointCard
{
    public string Method { get; set; } = "GET";

    public string Path { get; set; } = string.Empty;

    public string Parameters { get; set; } = string.Empty;

    public bool Table { get; set; } = true;

    public string Columns { get; set; } = string.Empty;

    /// <summary>The parameters ticked Needed (a typed "id*" ticks it too).</summary>
    public HashSet<string> Needed { get; } = [];

    /// <summary>A path's {word} names: always needed.</summary>
    public IReadOnlyList<string> InPath =>
        [.. PathWords().Matches(Path).Select(m => m.Groups[1].Value.Trim()).Where(w => w.Length > 0)];

    /// <summary>The parameter box's names ("status, id*": status, and id starred).</summary>
    public IReadOnlyList<(string Name, bool Starred)> Listed =>
        [.. Parameters.Split(',').Select(n => n.Trim()).Where(n => n.Length > 0)
            .Select(n => (Name: n.TrimEnd('*').Trim(), Starred: n.EndsWith('*')))
            .Where(n => n.Name.Length > 0)];

    /// <summary>Every parameter a Needed chip is drawn for: the path's first, then the box's.</summary>
    public IReadOnlyList<string> AllParameters => [.. InPath.Concat(Listed.Select(n => n.Name)).Distinct()];

    public bool IsNeeded(string name) => InPath.Contains(name) || Needed.Contains(name) || Listed.Any(n => n.Name == name && n.Starred);

    /// <summary>Why Try it cannot run, or empty when it can.</summary>
    public string TryReason
    {
        get
        {
            var asked = InPath.Count > 0 || Listed.Any(n => IsNeeded(n.Name));
            return Method != "GET" ? "Only a GET is tried"
                : !Table ? "Tick Read as a table to try it"
                : asked ? "It needs a value for a parameter"
                : Path.Trim().Length == 0 ? "Give it a path"
                : string.Empty;
        }
    }

    /// <summary>The card as Add API's form sends it.</summary>
    public Dictionary<string, object?> Sent()
    {
        var sent = new Dictionary<string, object?>
        {
            ["method"] = Method,
            ["path"] = Path.Trim(),
            ["parameters"] = string.Join(", ", Listed.Select(n => IsNeeded(n.Name) ? $"{n.Name}*" : n.Name)),
            ["table"] = Table,
        };
        if (Table && Columns.Trim().Length > 0)
        {
            sent["columns"] = Columns.Trim();
        }
        return sent;
    }

    [GeneratedRegex(@"\{([^{}]+)\}")]
    private static partial Regex PathWords();
}
