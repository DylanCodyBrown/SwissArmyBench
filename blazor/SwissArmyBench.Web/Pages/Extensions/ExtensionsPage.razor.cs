using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Extensions;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Extensions;

public partial class ExtensionsPage
{
    private const int WatchMilliseconds = 1500;
    private const int ServerError = 500;

    private readonly Dictionary<string, string> _said = [];
    private readonly CancellationTokenSource _gone = new();
    private ExtensionListing? _list;
    private Exception? _error;
    private ChangingExtension? _changing;
    private string _stage = string.Empty;
    private string? _busy;
    private bool _newing;
    private (ExtensionInfo Ext, string Question, string Action)? _asking;

    [Inject]
    private ExtensionsClient Extensions { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    protected override async Task OnInitializedAsync()
    {
        Live.NoticeArrived += OnNotice;
        await Js.InvokeVoidAsync("sab.setTitle", "Extensions");
        await LoadAsync();
    }

    private async Task LoadAsync()
    {
        if (_changing is not null)
        {
            return; // the server is going away: drawn from what was listed
        }
        try
        {
            _list = await Extensions.CardsAsync();
            _error = null;
            if (_list.Changing is { } changing)
            {
                Started(changing);
            }
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private static string StatusWords(ExtensionInfo ext) => ext.Source == "folder" ? "Installed (folder)" : ext.Status switch
    {
        "installed" when ext.Preinstalled => "Preinstalled",
        "installed" => "Installed",
        "available" => "Available",
        "coming" => "Coming",
        _ => ext.Status,
    };

    /// <summary>What its contract.json adds: the project type and the files a new project of it gets.</summary>
    private static string? ProjectLine(ExtensionInfo ext)
    {
        if (ext.ProjectType is null)
        {
            return null;
        }
        var named = (ext.Deliverable ?? []).Select(p => p.Replace("{slug}", "<name>", StringComparison.Ordinal)).ToList();
        return $"Adds the {ext.ProjectName ?? ext.ProjectType} project type{(named.Count > 0 ? $": {string.Join(", ", named)}" : string.Empty)}";
    }

    private string StageWords(string name, string action)
    {
        var doing = action == "install" ? $"Installing {name}" : $"Removing {name}";
        return _stage switch
        {
            "stopped" => $"{doing}: the app stopped; uv is at work.",
            "back" => $"{(action == "install" ? $"{name} is installed" : $"{name} is removed")}: the app opened again in a window of its own.",
            _ => $"{doing}: the app stops and starts again.",
        };
    }

    /// <summary>Install or Remove: the server asks first when it would (its question), else the change starts.</summary>
    private async Task ChangeAsync(ExtensionInfo ext, string action, bool confirmed)
    {
        _said.Remove(ext.Id);
        _busy = ext.Id;
        try
        {
            var answer = await Extensions.ChangeAsync(action, ext.Id, confirmed);
            if (answer.Confirm is { } question)
            {
                _asking = (ext, question, action);
            }
            else if (answer.Changing is { } changing)
            {
                Started(changing);
            }
            else if (answer.Removed is not null)
            {
                await LoadAsync(); // a folder's: gone at once, no restart
            }
        }
        catch (ApiException error)
        {
            _said[ext.Id] = error.Refusal.Error;
        }
        _busy = null;
    }

    private async Task ConfirmedAsync()
    {
        if (_asking is { } asking)
        {
            _asking = null;
            await ChangeAsync(asking.Ext, asking.Action, true);
        }
    }

    /// <summary>A folder extension loaded again (its missing packages installed first, when it has some).</summary>
    private async Task LoadAgainAsync(ExtensionInfo ext)
    {
        _busy = ext.Id;
        try
        {
            await Extensions.InstallAsync(ext.Id);
            await LoadAsync();
        }
        catch (ApiException error)
        {
            _said[ext.Id] = error.Refusal.Error;
        }
        _busy = null;
    }

    private async Task ShowAsync(ExtensionInfo ext)
    {
        try
        {
            await Extensions.ShowAsync(ext.Id);
        }
        catch (ApiException error)
        {
            _said[ext.Id] = error.Refusal.Error;
        }
    }

    private async Task NewDoneAsync(bool made)
    {
        _newing = false;
        if (made)
        {
            await LoadAsync();
        }
    }

    /// <summary>A change under way: the server is watched going away (uv at work) and coming back.</summary>
    private void Started(ChangingExtension changing)
    {
        if (_changing is not null)
        {
            return;
        }
        _changing = changing;
        _stage = string.Empty;
        _ = WatchAsync();
    }

    private async Task WatchAsync()
    {
        var stopped = false;
        while (!_gone.IsCancellationRequested)
        {
            try
            {
                await Task.Delay(WatchMilliseconds, _gone.Token);
            }
            catch (TaskCanceledException)
            {
                return;
            }
            var status = await Extensions.HealthAsync();
            if (status is 0 or >= ServerError)
            {
                stopped = true;
                _stage = "stopped";
            }
            else if (stopped)
            {
                _stage = status is 401 or 403 ? "back" : string.Empty;
                if (status == 200)
                {
                    _changing = null; // the same server answering again: the hand-over did not happen
                    await InvokeAsync(LoadAsync);
                }
                await InvokeAsync(StateHasChanged);
                return;
            }
            await InvokeAsync(StateHasChanged);
        }
    }

    private void OnNotice(Notice notice)
    {
        if (notice.Type is "extensions_changed" or "app_updating")
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
        _gone.Cancel();
        _gone.Dispose();
        GC.SuppressFinalize(this);
    }
}
