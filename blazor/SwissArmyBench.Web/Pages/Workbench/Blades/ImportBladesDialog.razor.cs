using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Forms;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Blades;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench.Blades;

public partial class ImportBladesDialog
{
    // A blade file (or a zip of them) is small text; larger is not one.
    private const long MaxFileBytes = 8 * 1024 * 1024;
    private const int MaxFiles = 50;

    private readonly Dictionary<string, string> _choices = [];
    private readonly Dictionary<string, Dictionary<string, Dictionary<string, string>>> _fill = [];
    private List<object> _files = [];
    private List<JsonElement>? _items;
    private List<string> _folders = [];
    private string _folder = string.Empty;
    private Exception? _error;

    [Inject]
    private BladesClient Blades { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Parameter]
    public EventCallback OnClose { get; set; }

    [Parameter]
    public EventCallback OnImported { get; set; }

    private int Importable => _items?.Count(i => i.TryGetProperty("blade", out var b) && b.ValueKind == JsonValueKind.Object) ?? 0;

    private static string Text(JsonElement e, string name) =>
        e.TryGetProperty(name, out var v) && v.ValueKind is not (JsonValueKind.Null or JsonValueKind.Undefined) ? v.ToString() : string.Empty;

    private static List<JsonElement> Settings(JsonElement item) =>
        item.TryGetProperty("settings", out var s) && s.ValueKind == JsonValueKind.Array ? s.EnumerateArray().ToList() : [];

    private static List<string> Secrets(JsonElement item) =>
        item.TryGetProperty("secrets", out var s) && s.ValueKind == JsonValueKind.Array ? s.EnumerateArray().Select(x => x.GetString() ?? string.Empty).ToList() : [];

    /// <summary>The files chosen, reviewed by the server (nothing saved or run).</summary>
    private async Task ChosenAsync(InputFileChangeEventArgs e)
    {
        try
        {
            var files = new List<object>();
            foreach (var file in e.GetMultipleFiles(MaxFiles))
            {
                using var stream = file.OpenReadStream(MaxFileBytes);
                using var memory = new MemoryStream();
                await stream.CopyToAsync(memory);
                files.Add(new { name = file.Name, data = Convert.ToBase64String(memory.ToArray()) });
            }
            _files = files;
            var preview = await Blades.ImportAsync(new { files });
            _items = preview.GetProperty("items").EnumerateArray().Select(i => i.Clone()).ToList();
            foreach (var item in _items.Where(i => i.TryGetProperty("blade", out var b) && b.ValueKind == JsonValueKind.Object))
            {
                _choices[item.GetProperty("index").ToString()] = item.TryGetProperty("conflict", out var c) && c.ValueKind == JsonValueKind.Object ? "copy" : "save";
            }
            var folders = await Blades.FoldersAsync();
            _folders = folders.GetProperty("folders").EnumerateArray()
                .Where(f => f.TryGetProperty("exists", out var x) && x.GetBoolean())
                .Select(f => f.GetProperty("path").GetString() ?? string.Empty).ToList();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private Dictionary<string, Dictionary<string, string>> Fill(string index) =>
        _fill.TryGetValue(index, out var f) ? f : _fill[index] = new() { ["settings"] = [], ["secrets"] = [] };

    private void SetSetting(string index, string id, string? value) => Fill(index)["settings"][id] = value ?? string.Empty;

    private void Choose(string index, ChangeEventArgs e) => _choices[index] = e.Value?.ToString() ?? "copy";

    private void Suggest(string index, string id, JsonElement suggestion) => SetSetting(index, id, Text(suggestion, "value"));

    private void SetSecret(string index, string secret, string? value) => Fill(index)["secrets"][secret] = value ?? string.Empty;

    private async Task ImportAsync()
    {
        try
        {
            var answer = await Blades.ImportAsync(new { files = _files, apply = true, choices = _choices, fill = _fill, folder = _folder.Length == 0 ? null : _folder });
            var results = answer.GetProperty("results").EnumerateArray().ToList();
            var saved = results.Where(r => Text(r, "status") == "saved").Select(r => Text(r, "name")).ToList();
            await Notes.SayAsync($"Imported {saved.Count} blade{(saved.Count == 1 ? string.Empty : "s")}{(saved.Count > 0 ? ": " + string.Join(", ", saved) : string.Empty)}.");
            foreach (var problem in results.Where(r => Text(r, "status") == "error" || (Text(r, "status") == "saved" && Text(r, "message").Length > 0)))
            {
                await Notes.SayAsync($"{(Text(problem, "name") is { Length: > 0 } n ? n : Text(problem, "file"))}: {(Text(problem, "message") is { Length: > 0 } m ? m : "not imported")}");
            }
            await OnImported.InvokeAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }
}
