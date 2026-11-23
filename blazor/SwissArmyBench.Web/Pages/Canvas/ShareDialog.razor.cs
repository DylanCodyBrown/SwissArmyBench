using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Sharing;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Canvas;

public partial class ShareDialog
{
    // While signing in, devtunnel's answer comes from its own process: looked at again this often.
    private const int SignInLookMs = 1500;

    private SharingStatus? _status;
    private Exception? _error;
    private string? _busy;
    private PeriodicTimer? _timer;

    [Inject]
    private SharingClient Sharing { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Parameter, EditorRequired]
    public ShareTarget App { get; set; } = default!;

    [Parameter]
    public EventCallback OnClose { get; set; }

    private ShareState? Share => _status?.Shares.FirstOrDefault(s => s.Kind == App.Kind && s.App == App.Id);

    private string StateWord => _status switch
    {
        null => "loading",
        _ when Share is { State: "sharing", Url: not null } => "sharing",
        { Installed: false } => "install",
        { SigningIn: true } => "signing_in",
        { SignedIn: false } or { WorkAccount: false } => "sign_in",
        _ => "ready",
    };

    protected override async Task OnInitializedAsync()
    {
        Live.NoticeArrived += OnNotice;
        await DrawAsync();
        _ = LookWhileSigningInAsync();
    }

    private async Task DrawAsync(bool fresh = false)
    {
        try
        {
            _status = await Sharing.StatusAsync(App.Kind, App.Id, fresh);
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task LookWhileSigningInAsync()
    {
        _timer = new PeriodicTimer(TimeSpan.FromMilliseconds(SignInLookMs));
        try
        {
            while (await _timer.WaitForNextTickAsync())
            {
                if (StateWord == "signing_in")
                {
                    await InvokeAsync(async () => { await DrawAsync(fresh: true); StateHasChanged(); });
                }
            }
        }
        catch (ObjectDisposedException)
        {
            // the dialog closed
        }
    }

    private async Task ActAsync(string words, Func<Task> work)
    {
        _busy = words;
        try
        {
            await work();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
            _busy = null;
            return;
        }
        _busy = null;
        await DrawAsync();
    }

    private async Task CopyAsync(string text, string said)
    {
        var copied = await Js.InvokeAsync<bool>("sab.copy", text);
        await Notes.SayAsync(copied ? said : "Copy is blocked here: select the text and copy it.");
    }

    private async Task OpenAsync(string url) => await Js.InvokeVoidAsync("open", url, "_blank", "noopener");

    private void OnNotice(Notice notice)
    {
        if (notice.Type == "sharing_changed")
        {
            _ = InvokeAsync(async () => { await DrawAsync(); StateHasChanged(); });
        }
    }

    public void Dispose()
    {
        Live.NoticeArrived -= OnNotice;
        _timer?.Dispose();
    }
}
