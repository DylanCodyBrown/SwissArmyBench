using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.LocalApi;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Apis;

public sealed partial class LocalApiSection : IDisposable
{
    private const string PropsKey = "sab.localApi.props";
    private const int LogMilliseconds = 2000;
    private const int SettleMilliseconds = 200;

    private readonly CancellationTokenSource _gone = new();
    private LocalApiState? _state;
    private LocalApiLog? _log;
    private Exception? _error;
    private bool _props;
    private bool _newing;
    private bool _wizard;
    private bool _exporting;
    private (double X, double Y)? _menu;
    private IReadOnlyList<RealCheck>? _checks;
    private CancellationTokenSource? _settle;

    [Inject]
    private LocalApiClient LocalApi { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    private IReadOnlyList<MenuEntry> MoreEntries =>
    [
        new("New endpoint…", "plus", Redrawn(() => Task.FromResult(_wizard = true))),
        new("Will this work for real?", "check", Redrawn(CheckAsync)),
        new("Export…", "export", Redrawn(() => Task.FromResult(_exporting = true))),
    ];

    /// <summary>A menu line's work, then this section drawn again (the menu has closed by the time it ends).</summary>
    private Func<Task> Redrawn(Func<Task> work) => async () =>
    {
        await work();
        StateHasChanged();
    };

    protected override async Task OnInitializedAsync()
    {
        Live.NoticeArrived += OnNotice;
        _props = await Js.InvokeAsync<string?>("sab.recall", PropsKey) == "on";
        await DrawAsync();
        _ = ReadLogAsync();
    }

    private async Task DrawAsync()
    {
        try
        {
            _state = await LocalApi.StateAsync();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>The requests and the process's output, read every two seconds while it runs.</summary>
    private async Task ReadLogAsync()
    {
        while (!_gone.IsCancellationRequested)
        {
            if (_state?.Running is not null)
            {
                try
                {
                    _log = await LocalApi.LogAsync();
                    await InvokeAsync(StateHasChanged);
                }
                catch (ApiException)
                {
                    _log = null;
                }
            }
            try
            {
                await Task.Delay(LogMilliseconds, _gone.Token);
            }
            catch (TaskCanceledException)
            {
                return;
            }
        }
    }

    private static IEnumerable<LocalApiProblem> Problems(LocalApiState state) =>
        (state.Problems ?? []).Concat(state.Failed is { } failed ? [new LocalApiProblem(failed.Line ?? 1, failed.Error)] : []);

    private string ScriptHref(int line) => $"scripts?path={Uri.EscapeDataString(_state?.File ?? "API.py")}&line={line}";

    private static string CheckMark(string state) => state switch
    {
        "works" => "Works",
        "sandbox" => "Sandbox only",
        "differs" => "Differs",
        "unreadable" => "Could not read",
        _ => "Not checked",
    };

    private async Task WizardClosedAsync()
    {
        _wizard = false;
        await DrawAsync();
    }

    private async Task PropsAsync()
    {
        _props = !_props;
        await Js.InvokeVoidAsync("sab.remember", PropsKey, _props ? "on" : "off");
    }

    private Task ActAsync(string route) => GuardAsync(() => LocalApi.ActAsync(route));

    private Task StopAgentAsync() => GuardAsync(LocalApi.StopAgentWritesAsync);

    private Task SaveAsync(string key, string? value) =>
        GuardAsync(() => LocalApi.SettingsAsync(new Dictionary<string, string> { [key] = value ?? string.Empty }));

    private async Task CheckAsync()
    {
        try
        {
            _checks = (await LocalApi.CheckAsync()).Checks;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task NewDoneAsync(bool made)
    {
        _newing = false;
        if (made)
        {
            await DrawAsync();
        }
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
        await DrawAsync();
    }

    private void OnNotice(Notice notice)
    {
        if (notice.Type is not ("local_api_changed" or "project_changed" or "file_changed"))
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

    public void Dispose()
    {
        Live.NoticeArrived -= OnNotice;
        _gone.Cancel();
        _gone.Dispose();
        _settle?.Cancel();
        _settle?.Dispose();
    }
}
