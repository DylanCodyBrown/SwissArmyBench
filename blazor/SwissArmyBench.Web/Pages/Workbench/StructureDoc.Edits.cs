using System.Text.Json;

using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Workbench;

// A structure tab's edits and steps (the classic structureDoc.ts and structureDocMenus.ts): a node's right-click menu,
// Add key…'s small form, the tree's edits on the file itself (its text written again in its format), and Transform's
// steps (Pick, Filter…, Sort…, Flatten) that make a view of the file, each one's × taking it away; Open as table.
public partial class StructureDoc
{
    private static readonly string[] _filterTests = ["=", "!=", ">", ">=", "<", "<=", "contains", "starts with", "exists", "missing"];

    private (string Title, IReadOnlyList<StructureField> Fields, Func<IReadOnlyDictionary<string, string>, Task> Go)? _asking;

    private void NodeMenu(StructureNodeMenu at)
    {
        if (_through)
        {
            return; // the steps' result is a view, not the file: it is not edited
        }
        _selected = at.Path;
        List<MenuEntry> entries = [new("Copy path", "copy", CopyPathAsync)];
        if (PythonBeside)
        {
            entries.Add(new("Copy as code", "code", CopyCodeAsync));
        }
        entries.Add(MenuEntry.Separator);
        if (at.Value.ValueKind == JsonValueKind.Object)
        {
            entries.Add(new("Add key…", "plus", () => AddKey(at.Path)));
        }
        if (at.Path != StructurePath.Root)
        {
            entries.Add(new("Duplicate", "duplicate", () => EditAsync("duplicate", at.Path)));
            if (at.Index is { } index)
            {
                if (index > 0)
                {
                    entries.Add(new("Move up", "up", () => EditAsync("move", at.Path, new() { ["to"] = index - 1 })));
                }
                if (index < at.Siblings - 1)
                {
                    entries.Add(new("Move down", "down", () => EditAsync("move", at.Path, new() { ["to"] = index + 1 })));
                }
            }
            entries.Add(new("Delete", "trash", () => EditAsync("remove", at.Path)));
        }
        _menu = new ShownMenu($"{at.Path} actions", entries, at.X, at.Y);
    }

    private Task AddKey(string path)
    {
        _asking = ("Add key…", [new("key", "Key"), new("value", "Value (JSON, or plain text)", "\"\"")], v =>
            EditAsync("add", path, new() { ["key"] = v["key"], ["value"] = ParseValue(v["value"]) }));
        return Task.CompletedTask;
    }

    // A value typed: JSON when it reads as JSON, else the words as text (the classic parseValue).
    private static object? ParseValue(string typed)
    {
        try
        {
            return JsonSerializer.Deserialize<JsonElement>(typed);
        }
        catch (JsonException)
        {
            return typed;
        }
    }

    private async Task AnsweredAsync(IReadOnlyDictionary<string, string> values)
    {
        if (_asking is { } asking)
        {
            _asking = null;
            await asking.Go(values);
        }
    }

    /// <summary>An edit of the file (set, rename, remove, add, duplicate, move): its text written again.</summary>
    private Task EditAsync(string op, string path, Dictionary<string, object?>? more = null) => DoAsync(async () =>
    {
        if (_shown is null)
        {
            return;
        }
        var body = new Dictionary<string, object?>(more ?? []) { ["op"] = op, ["path"] = path };
        var done = await Structures.EditAsync(_shown.Id, body);
        if (op == "remove" && _selected.StartsWith(path, StringComparison.Ordinal))
        {
            _selected = StructureFind.Ancestors(path)[^1];
        }
        Took(done);
        _editorText = _current = done.Text ?? _sent;
        await TellDirtyAsync();
    });

    private void ShowTransform(MouseEventArgs at)
    {
        if (SelectedValue is not { } node)
        {
            return;
        }
        var path = _selected;
        var list = node.ValueKind == JsonValueKind.Array;
        var records = list && node.EnumerateArray().Any() && node.EnumerateArray().All(r => r.ValueKind == JsonValueKind.Object);
        var fields = records
            ? node.EnumerateArray().Take(50).SelectMany(r => r.EnumerateObject().Select(p => p.Name)).Distinct().ToList()
            : [];
        var first = fields.FirstOrDefault() ?? string.Empty;
        List<MenuEntry> entries = [];
        if (path != StructurePath.Root)
        {
            entries.Add(new("Pick: only this branch", "zoom", () => AddStepAsync(new() { ["op"] = "pick", ["path"] = path })));
        }
        if (list)
        {
            entries.Add(new("Filter…", "filter", () => Ask("Filter…",
                [new("field", "Field", first), new("test", "Test", "=", _filterTests), new("value", "Value")],
                v => AddStepAsync(new() { ["op"] = "filter", ["path"] = path, ["field"] = v["field"], ["test"] = v["test"], ["value"] = v["value"] }))));
            entries.Add(new("Sort…", "sortup", () => Ask("Sort…",
                [new("field", "Field", first), new("order", "Order", "Smallest first", ["Smallest first", "Largest first"])],
                v => AddStepAsync(new() { ["op"] = "sort", ["path"] = path, ["field"] = v["field"], ["descending"] = v["order"] == "Largest first" }))));
            if (records)
            {
                entries.Add(new("Flatten", "rows", () => AddStepAsync(new() { ["op"] = "flatten", ["path"] = path })));
            }
        }
        if (list && node.GetArrayLength() > 0 && (_through || (_shown?.Steps ?? []).Count == 0))
        {
            entries.Add(new("Open as table", "grids", () => OpenGridAsync(path)));
        }
        if (entries.Count == 0)
        {
            entries.Add(new("Pick a list or a branch to transform it", "info", () => Task.CompletedTask));
        }
        _menu = new ShownMenu("Transform", entries, at.ClientX, at.ClientY + 4);
    }

    private Task Ask(string title, IReadOnlyList<StructureField> fields, Func<IReadOnlyDictionary<string, string>, Task> go)
    {
        _asking = (title, fields, go);
        return Task.CompletedTask;
    }

    private Task AddStepAsync(Dictionary<string, object?> step) => DoAsync(async () =>
    {
        if (_shown is null)
        {
            return;
        }
        var done = await Structures.AddStepAsync(_shown.Id, step);
        _shown = done with { Text = _shown.Text, Steps = done.Steps ?? _shown.Steps };
        _through = true;
        _resultValue = done.Value;
    });

    private Task RemoveStepAsync(int index) => DoAsync(async () =>
    {
        if (_shown is null)
        {
            return;
        }
        var done = await Structures.RemoveStepAsync(_shown.Id, index);
        _shown = done with { Text = _shown.Text, Steps = done.Steps ?? [] };
        _resultValue = done.Value;
        _through = _through && (_shown.Steps ?? []).Count > 0;
    });

    private Task OpenGridAsync(string path) => DoAsync(async () =>
    {
        if (_shown is not null)
        {
            var made = await Structures.GridAsync(_shown.Id, path);
            _ = Notes.SayAsync($"Opened {made.Dataset} as a table ({made.Rows} rows).");
        }
    });
}
