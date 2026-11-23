using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Environment;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Environment;

public partial class EnvironmentPage : IDisposable
{
    private const string Table = "table";
    private const string Structure = "structure";
    private const string Setting = "setting";
    private const string Library = "library";
    private const int TypingPauseMilliseconds = 120;

    private static readonly string[] _kinds = [Table, "variable", Structure, Setting, Library];

    private static readonly Dictionary<string, string> _tabWords = new()
    {
        [Table] = "Tables",
        ["variable"] = "Variables",
        [Structure] = "Structures",
        [Setting] = "Settings and secrets",
        [Library] = "Libraries",
    };

    /// <summary>A tab named in an address: its kind, or the word the tab shows (at=settings, at=libraries).</summary>
    private static readonly Dictionary<string, string> _tabNames = new(StringComparer.OrdinalIgnoreCase)
    {
        ["tables"] = Table,
        ["variables"] = "variable",
        ["structures"] = Structure,
        ["settings"] = Setting,
        ["secrets"] = Setting,
        ["libraries"] = Library,
    };

    private readonly HashSet<string> _opened = [];
    private readonly Dictionary<string, IReadOnlyList<IReadOnlyList<string>>> _columnsOf = [];
    private readonly Dictionary<string, string> _revealed = [];
    private EnvironmentAnswer? _answer;
    private Exception? _error;
    private string _tab = Table;
    private string? _selected;
    private string _typed = string.Empty;
    private string _query = string.Empty;
    private CancellationTokenSource? _typing;
    private bool _folded;
    private bool _checking;
    private bool _pythonToo;
    private int _asked;
    private ElementReference _searchBox;
    private KeyVaultsSection? _vaults;
    private HashSet<string> _hidden = [];

    [Inject]
    private EnvironmentClient Environment { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [SupplyParameterFromQuery(Name = "at")]
    public string? At { get; set; }

    [SupplyParameterFromQuery(Name = "name")]
    public string? RowName { get; set; }

    private EnvironmentItem? Selected => _answer?.Items.FirstOrDefault(i => i.Id == _selected);

    private IReadOnlyList<string> OtherTabs =>
        _kinds.Where(k => k != _tab && (_answer?.Counts.GetValueOrDefault(k) ?? 0) > 0).ToList();

    private string EmptyWords => _query.Length > 0 ? $"Nothing in {_tabWords[_tab]} matches “{_query}”." : _tab switch
    {
        Table => "No tables yet. Add one on the Connections page, or make one in code.",
        "variable" => "No variables yet: they show here as your code makes them.",
        Structure => "No structures yet: open a JSON, YAML, XML or TOML file, or send one from code.",
        Setting => "No settings yet.",
        _ => "No libraries yet: Install a library… adds one to the project.",
    };

    /// <summary>The list's grid: the twist, the name, the tab's shown columns, the actions.</summary>
    private string ListColumns =>
        $"--env-cols: {string.Join(" ", new[] { "18px", "minmax(170px,1.3fr)" }.Concat(Shown(_tab).Select(c => c.Width)).Append("30px"))}";

    protected override async Task OnInitializedAsync()
    {
        Live.NoticeArrived += OnNotice;
        _folded = await Js.InvokeAsync<string?>("sab.recall", "env.viewer.page") == "1";
    }

    protected override async Task OnParametersSetAsync()
    {
        var tab = At is not null && _tabNames.TryGetValue(At, out var named) ? named : At is not null && _kinds.Contains(At) ? At : Table;
        var changed = tab != _tab || _answer is null;
        _tab = tab;
        _hidden = await HiddenAsync(_tab);
        if (RowName is { } row)
        {
            _selected = $"{_tab}:{row}";
        }
        if (_answer is null)
        {
            await LoadAsync();
        }
        if (changed && _tab == Library)
        {
            await CheckAsync();
        }
        await Js.InvokeVoidAsync("sab.setTitle", "Environment");
    }

    private async Task LoadAsync()
    {
        var mine = ++_asked;
        try
        {
            var got = await Environment.ListingAsync(_query);
            if (mine != _asked)
            {
                return;
            }
            _answer = got;
            _error = null;
            if (_tab == Setting && _vaults is not null)
            {
                await _vaults.RefreshAsync(); // a vault saved, renamed or read again: its card follows
            }
        }
        catch (ApiException error)
        {
            _error = error;
        }
        if (Selected is not { } chosen || chosen.Kind != _tab)
        {
            _selected = Rows(_tab).FirstOrDefault()?.Id;
        }
    }

    /// <summary>The Libraries tab asks the index for newer versions when it opens (never in the background).</summary>
    private async Task CheckAsync()
    {
        if (_checking || _answer?.Checked == true)
        {
            return;
        }
        _checking = true;
        try
        {
            await Environment.CheckLibrariesAsync();
            await LoadAsync();
        }
        catch (ApiException)
        {
            // The index cannot be reached: the libraries show without a newer version.
        }
        _checking = false;
    }

    private IReadOnlyList<EnvironmentItem> Rows(string kind) => (_answer?.Items ?? []).Where(i => i.Kind == kind).ToList();

    private IReadOnlyList<EnvColumn> Shown(string kind) => EnvColumn.Of[kind].Where(c => kind != _tab || !_hidden.Contains(c.Head)).ToList();

    private async Task<HashSet<string>> HiddenAsync(string kind) =>
        ((await Js.InvokeAsync<string?>("sab.recall", $"env.hidden.{kind}")) ?? string.Empty).Split('|', StringSplitOptions.RemoveEmptyEntries).ToHashSet();

    private IReadOnlyList<IReadOnlyList<string>> KidsOf(EnvironmentItem item) => _columnsOf.GetValueOrDefault(item.Id) ?? item.Kids ?? [];

    private bool IsOpen(EnvironmentItem item) => _opened.Contains(item.Id) || (_query.Length > 0 && item.Match is { Own: false, Kids.Count: > 0 });

    private static string PythonWords(EnvironmentPython python, EnvironmentAnswer answer) =>
        python.Own ? "the project's own (.venv)"
        : python.Status == "making" ? "this app's own (the project's is being made)"
        : answer.Project is not null ? "this app's own (the project has no .venv yet)"
        : "this app's own";

    private async Task SetTabAsync(string kind, string? name = null)
    {
        _tab = kind;
        _hidden = await HiddenAsync(kind);
        _selected = name is null ? Rows(kind).FirstOrDefault()?.Id : $"{kind}:{name}";
        Moved();
        if (kind == Library)
        {
            await CheckAsync();
        }
    }

    private void Select(string id, bool reveal = false)
    {
        var item = _answer?.Items.FirstOrDefault(i => i.Id == id);
        if (item is not null && item.Kind != _tab)
        {
            _tab = item.Kind;
        }
        _selected = id;
        if (reveal && _folded)
        {
            _folded = false;
        }
        Moved();
    }

    /// <summary>The tab and the row in the address, replaced (a row is a place, not a step back).</summary>
    private void Moved()
    {
        var name = Selected?.Name;
        Nav.NavigateTo($"environment?at={_tab}{(name is null ? string.Empty : $"&name={Uri.EscapeDataString(name)}")}", replace: true);
    }

    private async Task ToggleAsync(EnvironmentItem item, bool? to)
    {
        var open = to ?? !_opened.Contains(item.Id);
        if (open)
        {
            _opened.Add(item.Id);
        }
        else
        {
            _opened.Remove(item.Id);
        }
        _selected = item.Id;
        // A table's columns with their ranges and blanks: asked once, when the row first opens.
        if (open && item.Kind == Table && item.Open?.ValueKind == System.Text.Json.JsonValueKind.True && !_columnsOf.ContainsKey(item.Id))
        {
            try
            {
                _columnsOf[item.Id] = await Environment.ColumnsAsync(item.Name);
            }
            catch (ApiException)
            {
                // its kids as listed stay
            }
        }
    }

    private async Task FoldAsync()
    {
        _folded = !_folded;
        await Js.InvokeVoidAsync("sab.remember", "env.viewer.page", _folded ? "1" : "0");
    }

    private void OnNotice(Notice notice)
    {
        if (notice.Type == "environment_changed")
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
        GC.SuppressFinalize(this);
    }
}
