using System.Text.RegularExpressions;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Apis;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Apis;

public sealed partial class ApiLearnedSection : IDisposable
{
    private const int SettleMilliseconds = 200;

    /// <summary>The project's files a built function never goes into (the server refuses them too).</summary>
    private static readonly HashSet<string> _notScripts = ["API.py", "data.py", "adapter.py", "api_adapter.py", "connections.py", "sab_api.py"];

    private static readonly Dictionary<string, string> _maps = new()
    {
        ["table"] = "a table",
        ["grid"] = "a grid",
        ["detail"] = "a detail card",
        ["form"] = "a form",
        ["metric"] = "a metric",
        ["download"] = "a download",
        ["text"] = "text",
    };

    private ActionContract? _contract;
    private Exception? _error;
    private bool _running;
    private string? _building;
    private IReadOnlyList<string>? _scripts;
    private string _script = string.Empty;
    private string _newScript = "api_functions.py";
    private (string Title, string Code)? _code;
    private CancellationTokenSource? _settle;

    [Inject]
    private ApisClient Apis { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Parameter, EditorRequired]
    public string Api { get; set; } = string.Empty;

    /// <summary>The action (the operation's id).</summary>
    [Parameter, EditorRequired]
    public string Action { get; set; } = string.Empty;

    /// <summary>A write (POST, PUT, PATCH, DELETE): no Run here.</summary>
    [Parameter]
    public bool Writes { get; set; }

    /// <summary>The inputs as typed on the operation's form, for Run and Build.</summary>
    [Parameter]
    public Func<IReadOnlyDictionary<string, string>> Inputs { get; set; } = () => new Dictionary<string, string>();

    protected override void OnInitialized() => Live.NoticeArrived += OnNotice;

    protected override Task OnParametersSetAsync() => DrawAsync();

    private async Task DrawAsync()
    {
        try
        {
            _contract = (await Apis.DescribeAsync(Api, Action)).Contract;
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private static string MapsWords(ActionContract c) =>
        c.MapsTo.Count > 0 ? $" · maps to {string.Join(" or ", c.MapsTo.Select(m => _maps.GetValueOrDefault(m, m)))}" : string.Empty;

    private static string TypeWords(ActionField f) =>
        f.Type + (f.Format is { Length: > 0 } format && format != "mixed" ? (format == "text" ? " in text" : $" ({format})") : string.Empty)
        + (f.Empty ? ", can be empty" : string.Empty);

    private async Task AnswerAsync(ActionOffer offer, bool take)
    {
        await GuardAsync(() => Apis.OfferAsync(Api, Action, offer, take));
        await DrawAsync();
    }

    private async Task RunAsync()
    {
        _running = true;
        await GuardAsync(async () =>
        {
            var got = await Apis.RunActionAsync(Api, Action, Inputs());
            if (!got.Ok && got.Error is { } refused)
            {
                _error = new ApiException(got.Status, new Refusal(refused.Error), string.Empty);
                return;
            }
            var records = got.Records is { } r ? $", {r.Count} record{(r.Count == 1 ? string.Empty : "s")}" : string.Empty;
            _ = Notes.SayAsync($"{got.Status}: {got.Kind}{records} in {got.Paging.Pages} page{(got.Paging.Pages == 1 ? string.Empty : "s")}");
        });
        _running = false;
        await DrawAsync();
    }

    /// <summary>Script function: the script it goes into, one of the open project's or a new one; with no project
    /// open, the code is shown to copy.</summary>
    private Task PickScriptAsync() => GuardAsync(async () =>
    {
        var got = await Apis.ScriptsAsync();
        if (got.Project is null)
        {
            await BuildAsync("function");
            return;
        }
        _scripts = [.. got.Documents.Select(d => d.Path).Where(p => !_notScripts.Contains(p.Split('/')[^1]) && !ClientFile().IsMatch(p))];
        _script = _scripts.FirstOrDefault() ?? string.Empty;
    });

    private async Task PutItThereAsync()
    {
        var path = _script.Length > 0 ? _script : _newScript.Trim().Length > 0 ? _newScript.Trim() : "api_functions.py";
        _scripts = null;
        await BuildAsync("function", path);
    }

    /// <summary>Build: put where it belongs and opened there (Notebooks at the cell, Scripts at the line), else the
    /// code to copy, else the widget said.</summary>
    private async Task BuildAsync(string kind, string? path = null)
    {
        _building = kind;
        await GuardAsync(async () =>
        {
            var asked = new Dictionary<string, object?> { ["api"] = Api, ["action"] = Action, ["as"] = kind, ["inputs"] = Inputs() };
            if (path is not null)
            {
                asked["path"] = path;
            }
            var got = await Apis.BuildAsync(asked);
            if (got.Path is { } file)
            {
                var page = file.EndsWith(".ipynb", StringComparison.OrdinalIgnoreCase) ? "notebooks" : "scripts";
                var at = got.Cell is { } cell ? $"&cell={cell}" : got.Line is { } line ? $"&line={line}" : string.Empty;
                Nav.NavigateTo($"{page}?path={Uri.EscapeDataString(file)}{at}");
            }
            else if (got.Code is { } code)
            {
                _code = (kind == "cell" ? "A notebook cell" : "A script function", code);
            }
            else
            {
                _ = Notes.SayAsync($"Put {got.Widget} on {got.Canvas}.");
            }
        });
        _building = null;
    }

    private async Task CopyCodeAsync()
    {
        if (_code is { } shown && await Js.InvokeAsync<bool>("sab.copy", shown.Code))
        {
            _ = Notes.SayAsync("Copied: paste it where you want it");
        }
    }

    private async Task GuardAsync(Func<Task> work)
    {
        try
        {
            await work();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>Its shape learned or drifted elsewhere (the agent's run, a notebook's sab.run, Discover): shown here too.</summary>
    private void OnNotice(Notice notice)
    {
        if (notice.Type != "api_shape_changed" || notice.Text("api") != Api || (notice.Text("action") is { Length: > 0 } of && of != Action))
        {
            return;
        }
        _settle?.Cancel();
        _settle = new CancellationTokenSource();
        var token = _settle.Token;
        _ = InvokeAsync(async () =>
        {
            try
            {
                await Task.Delay(SettleMilliseconds, token);
            }
            catch (TaskCanceledException)
            {
                return;
            }
            await DrawAsync();
            StateHasChanged();
        });
    }

    [GeneratedRegex(@"(^|/)API_\w+\.py$")]
    private static partial Regex ClientFile();

    public void Dispose()
    {
        Live.NoticeArrived -= OnNotice;
        _settle?.Cancel();
        _settle?.Dispose();
    }
}
