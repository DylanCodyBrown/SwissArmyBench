using System.Text.Json;

using Microsoft.JSInterop;


namespace SwissArmyBench.Web.Pages.Structures;

/// <summary>A structure's steps and actions (the classic structuresPage.ts step, act, nodeActions, saveAs, lineage,
/// returnAsTable): each step one call, its answer the structure again.</summary>
public partial class StructuresPage
{
    private static readonly string[] _tests = ["=", "!=", ">", ">=", "<", "<=", "contains", "starts with", "exists", "missing"];

    private (string Title, IReadOnlyList<AskField> Fields, Func<IReadOnlyDictionary<string, string>, Task> Then)? _asking;

    private Task StepAsync(Dictionary<string, object?> step) => GuardAsync(async () =>
    {
        if (_doc is null)
        {
            return;
        }
        _doc = await Structures.StepAsync(_doc.Id, step);
        KeepSelection();
        _tabs = await Structures.TabsAsync();
    });

    /// <summary>An action (/undo, /redo, /steps/remove, /save, /run-again): the structure read again after it.</summary>
    private Task ActAsync(string path, object? body = null) => GuardAsync(async () =>
    {
        if (_doc is null)
        {
            return;
        }
        await Structures.ActAsync(_doc.Id, path, body ?? new { });
        _doc = await Structures.ShownAsync(_doc.Id);
        KeepSelection();
        _tabs = await Structures.TabsAsync();
    });

    private Task FormatAsync(string? format) => GuardAsync(async () =>
    {
        if (_doc is not null && format is not null)
        {
            _doc = await Structures.ChangeAsync(_doc.Id, new { format });
            _tabs = await Structures.TabsAsync();
        }
    });

    private async Task RunAgainAsync()
    {
        _busyWords = $"Calling {_doc?.Origin.Operation ?? _doc?.Name} again…";
        await ActAsync("/run-again");
        _busyWords = null;
    }

    private Task SaveAsync()
    {
        if (_doc?.Path is null)
        {
            SaveAs();
            return Task.CompletedTask;
        }
        return ActAsync("/save");
    }

    private void SaveAs()
    {
        if (_doc is not { } current)
        {
            return;
        }
        Ask("Save as", [new AskField("name", "Name", current.Name), new AskField("format", "Format", current.Format, _formats)], async v =>
        {
            var done = await Structures.SaveAsAsync(current.Id, v["name"], v["format"]);
            _ = Notes.SayAsync($"Saved {done.Written}");
            await LoadAsync();
        });
    }

    private Task LineageAsync() => GuardAsync(async () =>
    {
        if (_doc is not null)
        {
            _lineage = await Structures.LineageAsync(_doc.Id);
        }
    });

    private async Task CopyPathAsync(string where)
    {
        await Js.InvokeAsync<bool>("sab.copy", where);
        _ = Notes.SayAsync($"Copied {where}");
    }

    private Task OpenAsGridAsync(string where) => GuardAsync(async () =>
    {
        _busyWords = "Opening…";
        try
        {
            await ActAsync("/grid", new { path = where });
            _ = Notes.SayAsync("Opened as a grid");
        }
        finally
        {
            _busyWords = null;
        }
    });

    /// <summary>Return as table: its web call saved with Return as table on; then its name in DuckDB SQL and its query.</summary>
    private Task ReturnAsTableAsync(string at) => GuardAsync(async () =>
    {
        if (_doc is not { Origin: { Api: { } api, Operation: { } operation } } doc)
        {
            return;
        }
        var saved = await Structures.AsTableAsync(api, operation, new { as_table = true, structure = doc.Id, at });
        if (saved.SqlName is not null)
        {
            _asTable = (saved, api, operation);
        }
    });

    private void AskFilter(string where)
    {
        var fields = FieldsOf(_node);
        Ask("Filter", [new AskField("field", "Field", fields.FirstOrDefault() ?? string.Empty), new AskField("test", "Test", "=", _tests), new AskField("value", "Value")], v =>
            StepAsync(new() { ["op"] = "filter", ["path"] = where, ["field"] = v["field"], ["test"] = v["test"], ["value"] = v["value"] }));
    }

    private void AskSort(string where)
    {
        var fields = FieldsOf(_node);
        Ask("Sort", [new AskField("field", "Field", fields.FirstOrDefault() ?? string.Empty), new AskField("order", "Order", "Smallest first", ["Smallest first", "Largest first"])], v =>
            StepAsync(new() { ["op"] = "sort", ["path"] = where, ["field"] = v["field"], ["descending"] = v["order"] == "Largest first" }));
    }

    private void AskAddKey(string where) =>
        Ask("Add key", [new AskField("key", "Key"), new AskField("value", "Value", "\"\"")], v =>
            StepAsync(new() { ["op"] = "add", ["path"] = where, ["key"] = v["key"], ["value"] = ParseValue(v["value"]) }));

    private void AskRenameKey(string last) =>
        Ask("Rename key", [new AskField("to", "New name", last)], v =>
            StepAsync(new() { ["op"] = "rename", ["path"] = StructureTree.PathText(_selected.Take(_selected.Count - 1)), ["key"] = last, ["to"] = v["to"] }));

    private void AskSetValue(string where) =>
        Ask("Set value", [new AskField("value", "Value (JSON)", _node?.GetRawText() ?? string.Empty)], v =>
            StepAsync(new() { ["op"] = "set", ["path"] = where, ["value"] = ParseValue(v["value"]) }));

    private Task SetValueAsync((IReadOnlyList<object> Parts, JsonElement Value) edit) =>
        StepAsync(new() { ["op"] = "set", ["path"] = StructureTree.PathText(edit.Parts), ["value"] = edit.Value });

    private Task RenameKeyAsync((IReadOnlyList<object> Parts, string Key, string To) edit) =>
        StepAsync(new() { ["op"] = "rename", ["path"] = StructureTree.PathText(edit.Parts), ["key"] = edit.Key, ["to"] = edit.To });

    private void Ask(string title, IReadOnlyList<AskField> fields, Func<IReadOnlyDictionary<string, string>, Task> then) => _asking = (title, fields, then);

    private async Task AnsweredAsync(IReadOnlyDictionary<string, string>? values)
    {
        var asked = _asking;
        _asking = null;
        if (values is not null && asked is { } a)
        {
            await GuardAsync(() => a.Then(values));
        }
    }

    /// <summary>A list of records' fields (its first fifty records' keys).</summary>
    private static IReadOnlyList<string> FieldsOf(JsonElement? node) =>
        IsRecords(node) ? node!.Value.EnumerateArray().Take(50).SelectMany(r => r.EnumerateObject().Select(p => p.Name)).Distinct().ToList() : [];

    /// <summary>A value typed: JSON when it reads as JSON, else the text itself.</summary>
    private static object? ParseValue(string text)
    {
        try
        {
            return JsonDocument.Parse(text).RootElement.Clone();
        }
        catch (JsonException)
        {
            return text;
        }
    }
}
