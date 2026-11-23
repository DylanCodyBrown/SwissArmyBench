using System.Text.Json;
using System.Text.RegularExpressions;

using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>A structure's search and paths for its tab (the classic structurePaths.ts): every node whose key or value
/// holds the words (in any case, in the document's order), a path as Python (data["orders"][3]), a path's parent and
/// last index, and the ancestors of a path (their way unfolded).</summary>
public static partial class StructureFind
{
    public const int Limit = 1000;

    [GeneratedRegex(@"\.([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]|\[(""(?:[^""\\]|\\.)*"")\]")]
    private static partial Regex Part();

    public static IReadOnlyList<string> Matches(JsonElement root, string words)
    {
        var said = words.Trim();
        List<string> found = [];
        if (said.Length > 0)
        {
            Walk(root, StructurePath.Root, null, said, found);
        }
        return found;
    }

    private static void Walk(JsonElement node, string path, string? key, string said, List<string> found)
    {
        if (found.Count >= Limit)
        {
            return;
        }
        var leaf = node.ValueKind is not (JsonValueKind.Object or JsonValueKind.Array);
        var words = node.ValueKind == JsonValueKind.String ? node.GetString() ?? string.Empty : node.GetRawText();
        if ((key?.Contains(said, StringComparison.OrdinalIgnoreCase) ?? false) || (leaf && words.Contains(said, StringComparison.OrdinalIgnoreCase)))
        {
            found.Add(path);
        }
        if (node.ValueKind == JsonValueKind.Array)
        {
            var at = 0;
            foreach (var child in node.EnumerateArray())
            {
                Walk(child, StructurePath.Index(path, at++), null, said, found);
            }
        }
        else if (node.ValueKind == JsonValueKind.Object)
        {
            foreach (var property in node.EnumerateObject())
            {
                Walk(property.Value, StructurePath.Key(path, property.Name), property.Name, said, found);
            }
        }
    }

    /// <summary>A path's parts: a key as its name, an index as its number.</summary>
    public static IReadOnlyList<object> Parts(string path) =>
        Part().Matches(path)
            .Select(m => m.Groups[1].Success ? m.Groups[1].Value
                : m.Groups[2].Success ? int.Parse(m.Groups[2].Value, System.Globalization.CultureInfo.InvariantCulture)
                : (object)(JsonSerializer.Deserialize<string>(m.Groups[3].Value) ?? string.Empty))
            .ToList();

    /// <summary>Copy as code: the node read from the file's value in Python (data["orders"][3]["lines"]).</summary>
    public static string Code(string path, string variable = "data") =>
        variable + string.Concat(Parts(path).Select(p => p is int n ? $"[{n}]" : $"[{JsonSerializer.Serialize((string)p)}]"));

    /// <summary>Every path above this one, from the top (the ways a found node is unfolded along).</summary>
    public static IReadOnlyList<string> Ancestors(string path)
    {
        var at = StructurePath.Root;
        List<string> above = [at];
        foreach (var part in Parts(path).SkipLast(1))
        {
            at = part is int n ? StructurePath.Index(at, n) : StructurePath.Key(at, (string)part);
            above.Add(at);
        }
        return above;
    }

    /// <summary>The value at a path (null: not there any more).</summary>
    public static JsonElement? At(JsonElement root, string path)
    {
        var node = root;
        foreach (var part in Parts(path))
        {
            if (part is int n && node.ValueKind == JsonValueKind.Array && n < node.GetArrayLength())
            {
                node = node[n];
            }
            else if (part is string k && node.ValueKind == JsonValueKind.Object && node.TryGetProperty(k, out var child))
            {
                node = child;
            }
            else
            {
                return null;
            }
        }
        return node;
    }
}
