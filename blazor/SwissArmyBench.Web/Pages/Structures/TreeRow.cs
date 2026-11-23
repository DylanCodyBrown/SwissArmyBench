using System.Text.Json;

namespace SwissArmyBench.Web.Pages.Structures;

/// <summary>One drawn line of a structure's tree: the way to its node (keys and indexes), the path's text, its key's
/// words, its kind (object, list, text, number, true or false, null), its value's words or its count, its level;
/// or, with `More` set, a list's "Show more (N)" line.</summary>
public sealed record TreeRow(
    IReadOnlyList<object> Parts,
    string Id,
    string Key,
    string Kind,
    string Shown,
    int Count,
    int Level,
    bool Open,
    JsonElement Node,
    int More = 0)
{
    public bool Container => Kind is "object" or "list";

    public bool IsIndex => Parts.Count > 0 && Parts[^1] is int;

    /// <summary>A node's kind in the classic words (structureTree.ts kindOf).</summary>
    public static string KindOf(JsonElement node) => node.ValueKind switch
    {
        JsonValueKind.Object => "object",
        JsonValueKind.Array => "list",
        JsonValueKind.String => "text",
        JsonValueKind.Number => "number",
        JsonValueKind.True or JsonValueKind.False => "bool",
        _ => "null",
    };

    /// <summary>A leaf as the tree shows it: text in quotes, the rest as written.</summary>
    public static string ShownOf(JsonElement node) => node.ValueKind switch
    {
        JsonValueKind.String => JsonSerializer.Serialize(node.GetString()),
        JsonValueKind.Null => "null",
        _ => node.GetRawText(),
    };
}
