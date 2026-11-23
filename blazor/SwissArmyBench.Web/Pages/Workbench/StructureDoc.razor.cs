using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

public partial class StructureDoc
{
    private const string ViewKey = "structure.view";
    private const int SearchSettlesMs = 150;

    private static readonly (string View, string Label)[] _views = [("tree", "Tree"), ("text", "Text"), ("both", "Both")];

    private static readonly Dictionary<string, string> _formatNames = new() { ["json"] = "JSON", ["yaml"] = "YAML", ["xml"] = "XML", ["toml"] = "TOML" };

    private StructureTab? _shown;
    private JsonElement? _fileValue; // the file's value (its text's last good parse)
    private JsonElement? _resultValue; // through its steps
    private string _view = "tree";
    private bool _through;
    private string _selected = StructurePath.Root;
    private string _words = string.Empty;
    private string _lastWords = string.Empty;
    private IReadOnlyList<string> _matches = [];
    private int _matchAt = -1;
    private HashSet<string> _marked = [];
    private HashSet<string> _unfold = [];
    private int _searchAsked;
    private Exception? _error;
    private ShownMenu? _menu;

    [Inject]
    private StructureTabClient Structures { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    /// <summary>The structure's file (opened by it), or an open structure's id.</summary>
    [Parameter]
    public string? Path { get; set; }

    [Parameter]
    public string? Id { get; set; }

    /// <summary>A node to select as it opens ($.orders[3]).</summary>
    [Parameter]
    public string? At { get; set; }

    /// <summary>A Python document is open on the page (Copy as code is offered beside one).</summary>
    [Parameter]
    public bool PythonBeside { get; set; }

    /// <summary>The tab's unsaved dot.</summary>
    [Parameter]
    public EventCallback<bool> OnDirty { get; set; }

    /// <summary>Saved under another name (Save as): its new path.</summary>
    [Parameter]
    public EventCallback<string> OnRenamed { get; set; }

    /// <summary>Its file is gone and the user closes it.</summary>
    [Parameter]
    public EventCallback OnClose { get; set; }

    /// <summary>Opened: its id and its file (the page's tab keeps them).</summary>
    [Parameter]
    public EventCallback<StructureTab> OnOpened { get; set; }

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    public string? StructureId => _shown?.Id;

    private string FormatName => _formatNames.GetValueOrDefault(_shown?.Format ?? "json", "JSON");

    private string Language => _shown?.Format ?? "json";

    private JsonElement? ShownValue => _through && _resultValue is not null ? _resultValue : _fileValue;

    private JsonElement? SelectedValue => ShownValue is { } root ? StructureFind.At(root, _selected) : null;

    private string? Found => _matchAt >= 0 && _matchAt < _matches.Count ? _matches[_matchAt] : null;

    private string CountWords => _words.Trim().Length == 0 ? string.Empty
        : _matches.Count > 0 ? $"{_matchAt + 1} of {_matches.Count}{(_matches.Count >= StructureFind.Limit ? "+" : string.Empty)}"
        : "No matches";

    private string? TreeProblem => _shown?.TextError is { } error
        ? $"{error} The tree shows the last text that parsed."
        : _through ? _shown?.Error : null;

    protected override async Task OnInitializedAsync()
    {
        _view = await Js.InvokeAsync<string?>("sab.recall", ViewKey) is ("text" or "both") and var kept ? kept : "tree";
        _selected = At ?? StructurePath.Root;
        try
        {
            var first = Path is { } path ? await Structures.OpenAsync(path) : await Structures.GetAsync(Id ?? string.Empty, false);
            Took(first);
            _savedText = _editorText = _current = first.Text ?? string.Empty;
            _sent = _savedText;
            await OnOpened.InvokeAsync(first);
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>An answer of the server's taken in: its value into the tree, its error said over the tree.</summary>
    private void Took(StructureTab done, bool withText = true)
    {
        _shown = _shown is null ? done : done with { Steps = done.Steps ?? _shown.Steps, Text = done.Text ?? _shown.Text };
        _hash = done.Hash ?? _hash;
        if (withText && done.Text is { } text)
        {
            _sent = text;
        }
        if (done.Value is { } value && done.TextError is null && !_through)
        {
            _fileValue = value;
        }
        else if (done.Value is { } result && _through)
        {
            _resultValue = result;
        }
        if (_words.Trim().Length > 0)
        {
            RunSearch(false);
        }
    }

    public async Task SetViewAsync(string view)
    {
        _view = view;
        await Js.InvokeVoidAsync("sab.remember", ViewKey, view);
    }

    private async Task ShowThroughAsync(bool on)
    {
        if (on == _through || _shown is null)
        {
            return;
        }
        _through = on;
        if (on)
        {
            await DoAsync(async () => _resultValue = (await Structures.GetAsync(_shown.Id, true)).Value);
        }
    }

    // ----- the search -----

    private async Task SearchTypedAsync(ChangeEventArgs e)
    {
        _words = e.Value?.ToString() ?? string.Empty;
        var mine = ++_searchAsked;
        await Task.Delay(SearchSettlesMs);
        if (mine == _searchAsked)
        {
            RunSearch(true);
        }
    }

    private void SearchKeyAsync(KeyboardEventArgs e)
    {
        if (e.Key == "Enter")
        {
            _searchAsked++;
            if (_words.Trim() != _lastWords)
            {
                RunSearch(true);
            }
            else
            {
                Step(e.ShiftKey ? -1 : 1);
            }
        }
        else if (e.Key == "Escape" && _words.Length > 0)
        {
            _words = string.Empty;
            RunSearch(false);
        }
    }

    private void RunSearch(bool go)
    {
        _lastWords = _words.Trim();
        _matches = ShownValue is { } root ? StructureFind.Matches(root, _words) : [];
        _marked = [.. _matches];
        _matchAt = _matches.Count == 0 ? -1 : go || _matchAt < 0 || _matchAt >= _matches.Count ? 0 : _matchAt;
        if (go && Found is { } found)
        {
            Reveal(found);
        }
    }

    private void Reveal(string path)
    {
        _selected = path;
        _unfold = [.. StructureFind.Ancestors(path)];
    }

    /// <summary>The next (1) or previous (-1) match, its way unfolded.</summary>
    public (int Count, int At, string? Path) Step(int by)
    {
        if (_matches.Count == 0)
        {
            return (0, -1, null);
        }
        _matchAt = (_matchAt + by + _matches.Count) % _matches.Count;
        Reveal(_matches[_matchAt]);
        return (_matches.Count, _matchAt, _matches[_matchAt]);
    }

    /// <summary>The search box's words (the agent's structure.search): the matches and the first in front.</summary>
    public (int Count, int At) Search(string words)
    {
        _words = words;
        RunSearch(true);
        StateHasChanged();
        return (_matches.Count, _matchAt);
    }

    /// <summary>A node selected by its path, its way unfolded (structure.select).</summary>
    public string Select(string path)
    {
        Reveal(path);
        StateHasChanged();
        return StructureFind.Code(path);
    }

    /// <summary>What the agent reads of it (structure.state): its view, selection, search and problems.</summary>
    public object State() => new
    {
        id = _shown?.Id,
        path = _shown?.Path,
        view = _view,
        through = _through,
        selected = _selected,
        search = _words,
        matches = _matches.Count,
        problem = _shown?.TextError,
        dirty = Dirty,
    };

    private void ShowMore(MouseEventArgs at)
    {
        List<MenuEntry> entries =
        [
            new("Open on the Structures page", "structures", () =>
            {
                Nav.NavigateTo($"structures?id={Uri.EscapeDataString(_shown?.Id ?? string.Empty)}");
                return Task.CompletedTask;
            }),
            new("Copy path", "copy", CopyPathAsync),
            new("Copy as code", "code", CopyCodeAsync),
        ];
        _menu = new ShownMenu(string.Empty, entries, at.ClientX, at.ClientY + 4);
    }

    private async Task CopyPathAsync()
    {
        await Js.InvokeAsync<bool>("sab.copy", _selected);
        _ = Notes.SayAsync($"Copied {_selected}");
    }

    private async Task CopyCodeAsync()
    {
        var text = StructureFind.Code(_selected);
        await Js.InvokeAsync<bool>("sab.copy", text);
        _ = Notes.SayAsync($"Copied {text}");
    }

    private async Task DoAsync(Func<Task> action)
    {
        try
        {
            await action();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }
}
