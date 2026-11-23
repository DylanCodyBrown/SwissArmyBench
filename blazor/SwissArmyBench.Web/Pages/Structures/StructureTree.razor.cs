using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Structures;

public partial class StructureTree
{
    /// <summary>A list's items drawn at once; Show more adds five times as many.</summary>
    private const int Page = 200;
    private const int SearchBudget = 2000;

    private readonly Dictionary<string, bool> _open = [];
    private readonly Dictionary<string, int> _more = [];
    private string _selectedId = string.Empty;
    private (string Id, bool IsKey)? _editing;
    private string _editText = string.Empty;
    private string _editStart = string.Empty;
    private ElementReference _editBox;
    private bool _focusEdit;
    private string _words = string.Empty;

    [Parameter, EditorRequired]
    public JsonElement Value { get; set; }

    [Parameter]
    public string Label { get; set; } = "Tree";

    /// <summary>The levels open at first (a large structure: one).</summary>
    [Parameter]
    public int Depth { get; set; } = 2;

    /// <summary>The search's words (any case): marked, the way to each unfolded.</summary>
    [Parameter]
    public string Search { get; set; } = string.Empty;

    /// <summary>A node selected: the way to it and its value.</summary>
    [Parameter]
    public EventCallback<(IReadOnlyList<object> Parts, JsonElement Node)> OnSelect { get; set; }

    /// <summary>A value edited in place: the way to it and the new value.</summary>
    [Parameter]
    public EventCallback<(IReadOnlyList<object> Parts, JsonElement Value)> OnSet { get; set; }

    /// <summary>A key renamed in place: the way to its object, the key and the new name.</summary>
    [Parameter]
    public EventCallback<(IReadOnlyList<object> Parts, string Key, string To)> OnRename { get; set; }

    protected override void OnParametersSet() => _words = Search.Trim().ToLowerInvariant();

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (_focusEdit)
        {
            _focusEdit = false;
            await _editBox.FocusAsync();
        }
    }

    /// <summary>A way's text as the app writes it: $.orders[3].amount.</summary>
    public static string PathText(IEnumerable<object> parts) =>
        parts.Aggregate(StructurePath.Root, (at, part) => part is int i ? StructurePath.Index(at, i) : StructurePath.Key(at, (string)part));

    /// <summary>The visible lines, depth first.</summary>
    private IReadOnlyList<TreeRow> Rows()
    {
        var rows = new List<TreeRow>();
        Walk(rows, "$", Value, [], 0);
        return rows;
    }

    private void Walk(List<TreeRow> rows, string key, JsonElement node, IReadOnlyList<object> parts, int level)
    {
        var id = PathText(parts);
        var kind = TreeRow.KindOf(node);
        var container = kind is "object" or "list";
        var count = kind == "list" ? node.GetArrayLength() : kind == "object" ? node.EnumerateObject().Count() : 0;
        var open = _open.TryGetValue(id, out var kept) ? kept : level < Depth || (_words.Length > 0 && HasMatch(node, new[] { SearchBudget }));
        rows.Add(new TreeRow(parts, id, key, kind, container ? string.Empty : TreeRow.ShownOf(node), count, level, open, node));
        if (!container || !open)
        {
            return;
        }
        if (kind == "list")
        {
            var limit = _more.GetValueOrDefault(id, Page);
            foreach (var (child, i) in node.EnumerateArray().Take(limit).Select((c, i) => (c, i)))
            {
                Walk(rows, $"[{i}]", child, [.. parts, i], level + 1);
            }
            if (count > limit)
            {
                rows.Add(new TreeRow(parts, id, string.Empty, kind, string.Empty, count, level + 1, false, node, count - limit));
            }
            return;
        }
        foreach (var property in node.EnumerateObject())
        {
            Walk(rows, property.Name, property.Value, [.. parts, property.Name], level + 1);
        }
    }

    private bool HasMatch(JsonElement node, int[] budget)
    {
        if (_words.Length == 0 || budget[0]-- <= 0)
        {
            return false;
        }
        return node.ValueKind switch
        {
            JsonValueKind.Object => node.EnumerateObject().Any(p => p.Name.Contains(_words, StringComparison.OrdinalIgnoreCase) || HasMatch(p.Value, budget)),
            JsonValueKind.Array => node.EnumerateArray().Any(v => HasMatch(v, budget)),
            _ => TreeRow.ShownOf(node).Contains(_words, StringComparison.OrdinalIgnoreCase),
        };
    }

    private void Fold(TreeRow row) => _open[row.Id] = !row.Open;

    private void ShowMore(TreeRow row) => _more[row.Id] = _more.GetValueOrDefault(row.Id, Page) + (Page * 5);

    private async Task SelectAsync(TreeRow row)
    {
        _selectedId = row.Id;
        await OnSelect.InvokeAsync((row.Parts, row.Node));
    }

    private void EditValue(TreeRow row)
    {
        if (!OnSet.HasDelegate)
        {
            return;
        }
        _editStart = row.Node.ValueKind == JsonValueKind.String ? row.Node.GetString() ?? string.Empty : row.Node.GetRawText();
        (_editing, _editText, _focusEdit) = ((row.Id, false), _editStart, true);
    }

    private void EditKey(TreeRow row)
    {
        if (!OnRename.HasDelegate || row.Parts.Count == 0 || row.Parts[^1] is not string key)
        {
            return;
        }
        (_editing, _editStart, _editText, _focusEdit) = ((row.Id, true), key, key, true);
    }

    private async Task EditKeyAsync(KeyboardEventArgs e, TreeRow row, bool isKey)
    {
        if (e.Key is "Enter" or "Escape")
        {
            await FinishAsync(row, isKey, e.Key == "Enter");
        }
    }

    /// <summary>An edit kept (when it changed something) or left; a value that is not text is read as JSON.</summary>
    private async Task FinishAsync(TreeRow row, bool isKey, bool keep)
    {
        if (_editing != (row.Id, isKey))
        {
            return;
        }
        _editing = null;
        if (!keep || _editText == _editStart)
        {
            return;
        }
        if (isKey)
        {
            await OnRename.InvokeAsync((row.Parts.Take(row.Parts.Count - 1).ToList(), (string)row.Parts[^1], _editText));
            return;
        }
        await OnSet.InvokeAsync((row.Parts, Typed(row.Node, _editText)));
    }

    private static JsonElement Typed(JsonElement was, string text)
    {
        if (was.ValueKind != JsonValueKind.String)
        {
            try
            {
                return JsonDocument.Parse(text).RootElement.Clone();
            }
            catch (JsonException)
            {
                // text it is
            }
        }
        return JsonSerializer.SerializeToElement(text);
    }

    /// <summary>The arrows: Up and Down move the selection; Right and Left unfold and fold the selected node.</summary>
    private async Task KeyAsync(KeyboardEventArgs e)
    {
        if (_editing is not null)
        {
            return;
        }
        var rows = Rows().Where(r => r.More == 0).ToList();
        var at = rows.FindIndex(r => r.Id == _selectedId);
        switch (e.Key)
        {
            case "ArrowDown":
                await SelectAsync(rows[Math.Min(rows.Count - 1, at + 1)]);
                break;
            case "ArrowUp":
                await SelectAsync(rows[Math.Max(0, at - 1)]);
                break;
            case "ArrowRight" or "ArrowLeft" when at >= 0:
                _open[rows[at].Id] = e.Key == "ArrowRight";
                break;
            default:
                break;
        }
    }
}
