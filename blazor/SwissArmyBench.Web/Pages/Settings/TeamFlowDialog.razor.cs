using System.Globalization;
using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Settings;

namespace SwissArmyBench.Web.Pages.Settings;

public sealed partial class TeamFlowDialog : IDisposable
{
    private const int DefaultPollSeconds = 5;

    private readonly CancellationTokenSource _closing = new();
    private string _at = string.Empty;
    private TeamStatus? _status;
    private Exception? _error;
    private string? _busyWords;
    private bool _installing;
    private (string UserCode, string Uri)? _code;
    private string _token = string.Empty;
    private IReadOnlyList<TeamRepository> _repositories = [];
    private string _search = string.Empty;
    private IReadOnlyList<string> _owners = [];
    private string _owner = string.Empty;
    private string _name = "team-library";
    private string _joined = string.Empty;

    [Inject]
    private SettingsClient Settings { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    /// <summary>"join" or "start".</summary>
    [Parameter, EditorRequired]
    public string Action { get; set; } = "join";

    [Parameter]
    public EventCallback OnClose { get; set; }

    private IReadOnlyList<(string Key, string Name)> Steps => Action == "join"
        ? [("install", "GitHub sync"), ("sign_in", "Sign in"), ("pick", "Repository"), ("setup", "Set up")]
        : [("install", "GitHub sync"), ("sign_in", "Sign in"), ("name", "Name"), ("setup", "Set up")];

    private IReadOnlyList<TeamRepository> Shown
    {
        get
        {
            var words = _search.ToLowerInvariant().Split(' ', StringSplitOptions.RemoveEmptyEntries);
            return _repositories.Where(r => words.All(w => r.Repository.Contains(w, StringComparison.OrdinalIgnoreCase))).ToList();
        }
    }

    protected override Task OnInitializedAsync() => NextAsync();

    private static string Day(string iso) =>
        DateTimeOffset.TryParse(iso, CultureInfo.InvariantCulture, DateTimeStyles.None, out var at) ? at.ToLocalTime().ToString("d", CultureInfo.CurrentCulture) : string.Empty;

    /// <summary>The first step still to do, as the server says this computer is.</summary>
    private async Task NextAsync()
    {
        await GuardAsync("Looking at this computer…", async () =>
        {
            _status = await Settings.TeamAsync();
            _at = !_status.SyncOn ? "install" : !_status.SignedIn ? "sign_in" : Action == "join" ? "pick" : "name";
        });
        if (_at == "pick")
        {
            await GuardAsync("Asking GitHub for your repositories…", async () => _repositories = (await Settings.TeamRepositoriesAsync()).Repositories);
        }
        else if (_at == "name")
        {
            await GuardAsync("Asking GitHub who can own it…", async () =>
            {
                _owners = (await Settings.TeamOwnersAsync()).Owners;
                _owner = _owners.FirstOrDefault() ?? string.Empty;
            });
        }
    }

    /// <summary>Install GitHub sync: the step kept over the app's restart, then Settings opens here again.</summary>
    private async Task InstallAsync()
    {
        await GuardAsync("Installing…", async () =>
        {
            await Settings.TeamPendingAsync(Action);
            try
            {
                var done = await Settings.InstallExtensionAsync(_status?.Needs?.Id ?? "git");
                _installing = done.TryGetProperty("changing", out var changing) && changing.ValueKind != JsonValueKind.Null;
            }
            catch (ApiException)
            {
                await Settings.TeamPendingAsync(null);
                throw;
            }
        });
    }

    private async Task DeviceAsync()
    {
        try
        {
            var got = await Settings.SignInDeviceAsync();
            _code = (got.GetProperty("user_code").GetString() ?? string.Empty, got.GetProperty("verification_uri").GetString() ?? string.Empty);
            await Js.InvokeVoidAsync("open", _code.Value.Uri, "_blank", "noopener");
            var every = got.TryGetProperty("interval", out var interval) ? interval.GetInt32() : DefaultPollSeconds;
            _ = PollAsync(every);
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task PollAsync(int seconds)
    {
        while (!_closing.IsCancellationRequested)
        {
            try
            {
                await Task.Delay(TimeSpan.FromSeconds(seconds), _closing.Token);
                var answer = await Settings.SignInPollAsync();
                var state = answer.GetProperty("state").GetString();
                if (state == "signed_in")
                {
                    await InvokeAsync(NextAsync);
                    await InvokeAsync(StateHasChanged);
                    return;
                }
                if (state != "pending")
                {
                    _code = (answer.TryGetProperty("words", out var words) ? words.GetString() ?? state ?? string.Empty : state ?? string.Empty, string.Empty);
                    await InvokeAsync(StateHasChanged);
                    return;
                }
                seconds = answer.TryGetProperty("interval", out var next) ? next.GetInt32() : seconds;
            }
            catch (TaskCanceledException)
            {
                return;
            }
            catch (ApiException error)
            {
                _error = error;
                await InvokeAsync(StateHasChanged);
                return;
            }
        }
    }

    private async Task TokenKeyAsync(KeyboardEventArgs e)
    {
        if (e.Key == "Enter" && _token.Trim().Length > 0)
        {
            await UseTokenAsync();
        }
    }

    private async Task UseTokenAsync()
    {
        if (_token.Trim().Length == 0)
        {
            return;
        }
        await GuardAsync("Signing in…", async () =>
        {
            await Settings.SignInWithTokenAsync(_token.Trim());
            _token = string.Empty;
        });
        if (_error is null)
        {
            await NextAsync();
        }
    }

    private async Task SearchKeyAsync(KeyboardEventArgs e)
    {
        if (e.Key == "Enter" && Shown.FirstOrDefault() is { } first)
        {
            await JoinAsync(first.Repository);
        }
    }

    private Task JoinAsync(string repository) => GuardAsync($"Copying {repository}…", async () =>
    {
        await Settings.TeamJoinAsync(repository);
        (_joined, _at) = (repository, "setup");
    });

    private async Task NameKeyAsync(KeyboardEventArgs e)
    {
        if (e.Key == "Enter")
        {
            await StartAsync();
        }
    }

    private Task StartAsync() => GuardAsync($"Making {_owner}/{_name.Trim()} on GitHub…", async () =>
    {
        var done = await Settings.TeamStartAsync(_name, _owner == _status?.Account ? null : _owner);
        (_joined, _at) = (done.Started ?? $"{_owner}/{_name.Trim()}", "setup");
    });

    private async Task GuardAsync(string words, Func<Task> work)
    {
        _busyWords = words;
        try
        {
            await work();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _busyWords = null;
    }

    public void Dispose()
    {
        _closing.Cancel();
        _closing.Dispose();
    }
}
