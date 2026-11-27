using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Files;
using SwissArmyBench.Web.Api.Structures;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Structures;

public partial class StructuresPage
{
    private const int TextPauseMilliseconds = 500;
    private const int Kilobyte = 1024;

    private static readonly string[] _formats = ["json", "yaml", "xml", "toml"];
    private static readonly (string View, string Label)[] _views = [("tree", "Tree"), ("both", "Both"), ("text", "Text")];

    private readonly Dictionary<string, string> _used = [];
    private StructureTabs? _tabs;
    private StructureShown? _doc;
    private string? _front;
    private Exception? _error;
    private string? _busyWords;
    private string _view = "both";
    private string _search = string.Empty;
    private IReadOnlyList<object> _selected = [];
    private JsonElement? _node;
    private string? _textError;
    private bool _pasting;
    private CancellationTokenSource? _typing;
    private string? _variantPath;
    private StructureLineage? _lineage;
    private (ReturnedAsTable Saved, string Api, string Operation)? _asTable;

    [Inject]
    private StructuresClient Structures { get; set; } = default!;

    [Inject]
    private FileChooser Files { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    /// <summary>A structure to bring to the front (?id=).</summary>
    [SupplyParameterFromQuery(Name = "id")]
    public string? IdParameter { get; set; }

    /// <summary>A structure file to open and bring to the front (?path=: the Environment's row).</summary>
    [SupplyParameterFromQuery(Name = "path")]
    public string? PathParameter { get; set; }

    protected override void OnInitialized() => Live.NoticeArrived += OnNotice;

    protected override async Task OnParametersSetAsync()
    {
        _front = IdParameter ?? _front;
        if (PathParameter is { } path)
        {
            await GuardAsync(async () => _front = (await Structures.OpenShownAsync(path)).Id);
        }
        await LoadAsync();
        await Js.InvokeVoidAsync("sab.setTitle", "Structures");
    }

    private async Task LoadAsync()
    {
        await GuardAsync(async () =>
        {
            _tabs = await Structures.TabsAsync();
            if (_front is null || _tabs.Open.All(s => s.Id != _front))
            {
                _front = _tabs.Open.LastOrDefault()?.Id;
            }
            _doc = _front is null ? null : await Structures.ShownAsync(_front);
            _textError = null;
            KeepSelection();
            await CountUsesAsync();
        });
    }

    /// <summary>The selected node stays selected while it is still there.</summary>
    private void KeepSelection()
    {
        _node = _doc?.Value is { } value ? At(value, _selected) : null;
        if (_node is null)
        {
            _selected = [];
            _node = _doc?.Value;
        }
    }

    /// <summary>A node by its way (keys and indexes), or null when it is not there.</summary>
    private static JsonElement? At(JsonElement root, IReadOnlyList<object> parts)
    {
        var node = root;
        foreach (var part in parts)
        {
            var next = part switch
            {
                int i when node.ValueKind == JsonValueKind.Array && i < node.GetArrayLength() => node[i],
                string key when node.ValueKind == JsonValueKind.Object && node.TryGetProperty(key, out var child) => child,
                _ => (JsonElement?)null,
            };
            if (next is not { } found)
            {
                return null;
            }
            node = found;
        }
        return node;
    }

    private async Task CountUsesAsync()
    {
        foreach (var file in (_tabs?.Files ?? []).Where(f => !_used.ContainsKey(f.Name)))
        {
            try
            {
                var n = await Structures.ReferencesAsync(file.Name);
                _used[file.Name] = n > 0 ? $"used in {n} place{(n == 1 ? string.Empty : "s")}" : string.Empty;
            }
            catch (ApiException)
            {
                _used[file.Name] = string.Empty;
            }
        }
    }

    private string UsedWords(string name) => _used.GetValueOrDefault(name) ?? string.Empty;

    private static string FormatWords(string format) => format switch
    {
        "json" => "JSON",
        "yaml" => "YAML",
        "xml" => "XML",
        "toml" => "TOML",
        _ => format,
    };

    private static string EditorLanguage(string format) => format is "json" or "yaml" or "xml" ? format : "plaintext";

    private static string SizeWords(long bytes) =>
        bytes < Kilobyte ? $"{bytes} B" : bytes < Kilobyte * Kilobyte ? $"{Math.Round(bytes / (double)Kilobyte)} KB" : $"{bytes / (double)(Kilobyte * Kilobyte):0.0} MB";

    private static string TextKey(StructureShown doc) => $"{doc.Id}-{doc.Version}-{doc.Steps.Count}-{doc.Format}";

    private static string SentText(JsonElement origin) =>
        JsonSerializer.Serialize(
            new
            {
                inputs = origin.TryGetProperty("inputs", out var i) ? i : default,
                body = origin.TryGetProperty("body", out var b) ? b : default,
                at = origin.TryGetProperty("at", out var a) ? a : default,
            },
            new JsonSerializerOptions { WriteIndented = true });

    private static bool IsRecords(JsonElement? node) =>
        node is { ValueKind: JsonValueKind.Array } list && list.GetArrayLength() > 0 && list.EnumerateArray().All(r => r.ValueKind == JsonValueKind.Object);

    private async Task GoAsync(string id)
    {
        _front = id;
        _selected = [];
        await LoadAsync();
    }

    // New: a new JSON file through the one New file dialog (the Scripts page's: its name first, written by the
    // server, opened there as a structure's tab). There is no untitled structure.
    private const string NewAddress = "scripts?new=json";

    private async Task OpenFileAsync()
    {
        var path = await Files.ChooseAsync("file", "Open a structure", null, "structure", [".json", ".yaml", ".yml", ".xml", ".toml"]);
        if (path is not null)
        {
            await OpenPathAsync(path);
        }
    }

    private Task OpenPathAsync(string path) => GuardAsync(async () => await GoAsync((await Structures.OpenShownAsync(path)).Id));

    private async Task PastedAsync(string? id)
    {
        _pasting = false;
        if (id is not null)
        {
            await GoAsync(id);
        }
    }

    private async Task CloseAsync(StructureShown s)
    {
        if (s.Dirty && !await Dialogs.AskYesNoAsync($"Close {s.Name}", $"{s.Name} has changes that are not saved. Close it?", "Close"))
        {
            return;
        }
        await GuardAsync(async () =>
        {
            await Structures.CloseAsync(s.Id);
            if (_front == s.Id)
            {
                _front = null;
            }
            await LoadAsync();
        });
    }

    private void Selected((IReadOnlyList<object> Parts, JsonElement Node) at) => (_selected, _node) = (at.Parts, at.Node);

    /// <summary>The text typed (no steps): sent once typing pauses; its error said at its line, the tree follows.</summary>
    private void TextTyped(string text)
    {
        _typing?.Cancel();
        _typing = new CancellationTokenSource();
        var token = _typing.Token;
        var id = _doc?.Id;
        _ = InvokeAsync(async () =>
        {
            try
            {
                await Task.Delay(TextPauseMilliseconds, token);
            }
            catch (TaskCanceledException)
            {
                return;
            }
            if (id is null)
            {
                return;
            }
            try
            {
                var done = await Structures.ChangeAsync(id, new { text, view = "result" });
                _textError = done.TextError;
                if (done.TextError is null)
                {
                    _doc = done with { Text = text };
                    _tabs = await Structures.TabsAsync();
                }
            }
            catch (ApiException error)
            {
                _textError = error.Refusal.Error;
            }
            StateHasChanged();
        });
    }

    private async Task GuardAsync(Func<Task> work)
    {
        try
        {
            await work();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private void OnNotice(Notice notice)
    {
        if (notice.Type == "structures_changed")
        {
            _ = InvokeAsync(async () =>
            {
                await LoadAsync();
                StateHasChanged();
            });
        }
    }

    public void Dispose()
    {
        Live.NoticeArrived -= OnNotice;
        _typing?.Cancel();
        _typing?.Dispose();
    }
}
