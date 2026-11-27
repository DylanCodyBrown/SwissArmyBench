using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Routing;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.App;

namespace SwissArmyBench.Web.State;

/// <summary>
/// Pop out (the owner, 2026-11-27: "I should be able to pop out any page or any grid into a new tab of its own and
/// that grid or page should go blank on the original app with a reattach button in the pane to bring it back"):
/// which window holds each popped-out page, table or document. The server keeps the list in memory and tells every
/// window (the pop_outs notice); this service is one window's view of it. A popped-out window (<see cref="Own"/>,
/// from its name sab-pop:&lt;key&gt;) says its key and where it is on the live socket as it opens and as it moves,
/// and closes itself once its key is brought back; any other window shows the placeholder where the page or table
/// was (<see cref="Elsewhere"/>). Its value raises one Changed.
/// </summary>
public sealed class PopOuts : IDisposable
{
    private const string ListNotice = "pop_outs";
    private const string ShowNotice = "pop_out_show";
    private const string OpenNotice = "pop_out_open";
    private const string FrontNotice = "pop_out_front";
    private const string Said = "pop_out";

    private readonly AppClient _app;
    private readonly IJSRuntime _js;
    private readonly LiveUpdates _live;
    private readonly NavigationManager _nav;
    private readonly ScreenState _screen;
    private readonly Notes _notes;
    private DotNetObjectReference<PopOuts>? _self;
    private string? _ownName;
    private bool _held;
    private bool _started;
    private bool _leavingOwn;

    public PopOuts(AppClient app, IJSRuntime js, LiveUpdates live, NavigationManager nav, ScreenState screen, Notes notes)
    {
        _app = app;
        _js = js;
        _live = live;
        _nav = nav;
        _screen = screen;
        _notes = notes;
    }

    public event Action? Changed;

    /// <summary>What a popped-out window does before it closes itself (a document saves what is unsaved).</summary>
    public Func<Task>? BeforeClose { get; set; }

    /// <summary>A page's own state as its address, when its address alone does not say it (the Settings page's
    /// section in view): what a pop-out opens at and what Reattach brings back. Null: the address as it is.</summary>
    public Func<string>? StateAddress { get; set; }

    /// <summary>Where this window is now, with the page's own state.</summary>
    public string AddressNow => StateAddress?.Invoke() ?? Here;

    /// <summary>The key this window holds: it is a popped-out window. Null for a main window.</summary>
    public string? Own { get; private set; }

    public IReadOnlyList<PopOutEntry> Popped { get; private set; } = [];

    /// <summary>How many main windows are open (none: a popped-out window's Reattach opens one).</summary>
    public int Mains { get; private set; }

    private string Here => _nav.ToBaseRelativePath(_nav.Uri);

    /// <summary>A page's own state moved (<see cref="StateAddress"/>): a popped-out window says where it is now.</summary>
    public void Touch() => _ = SayOwnAsync();

    /// <summary>Read which window this is and what is popped out, then follow the notices (once a window).</summary>
    public async Task StartAsync()
    {
        if (_started)
        {
            return;
        }
        _started = true;
        var own = await _js.InvokeAsync<string?>("sab.popOut.own");
        Own = string.IsNullOrEmpty(own) ? null : own;
        _self = DotNetObjectReference.Create(this);
        _live.NoticeArrived += OnNotice;
        _live.Changed += OnSocket;
        _nav.LocationChanged += OnMoved;
        _screen.Show(this, ScreenPart);
        try
        {
            Take(await _app.PopOutsAsync());
        }
        catch (ApiException)
        {
            // The list did not come: the next notice brings it.
        }
        if (Own is { } key)
        {
            _ownName = Popped.FirstOrDefault(e => e.Key == key)?.Name ?? key[(key.IndexOf(':', StringComparison.Ordinal) + 1)..];
            await _js.InvokeVoidAsync("sab.popOut.mark", key.Split(':')[0]);
            await SayOwnAsync();
        }
        Changed?.Invoke();
    }

    /// <summary>The entry of `key` when it is live in another window: this one shows the placeholder there.</summary>
    public PopOutEntry? Elsewhere(string key) => key == Own ? null : Popped.FirstOrDefault(e => e.Key == key);

    /// <summary>Pop a page, a table or a document out: its own window (the desktop app's), its own tab (a
    /// browser's). Already out: that window comes to the front.</summary>
    public async Task PopAsync(string key, string name, string address)
    {
        try
        {
            var entry = await _app.PopOutAsync(key, name, address);
            if (entry.Existing)
            {
                await _js.InvokeVoidAsync("sab.popOut.show", key);
            }
            else if (!await _js.InvokeAsync<bool>("sab.popOut.open", key, address, _self))
            {
                await _app.ReattachAsync(key, front: false);
                _notes.Error(new InvalidOperationException("The browser blocked the new window: allow pop-ups for this address."));
            }
        }
        catch (ApiException error)
        {
            _notes.Error(error);
        }
    }

    /// <summary>Bring it back to its old place (the placeholder's Reattach): its window closes.</summary>
    public async Task ReattachAsync(string key)
    {
        try
        {
            await _app.ReattachAsync(key, front: false);
        }
        catch (ApiException error) when (error.Status == 404)
        {
            // Back already (its window closed, another window's Reattach).
        }
        catch (ApiException error)
        {
            _notes.Error(error);
        }
        await _js.InvokeVoidAsync("sab.popOut.close", key);
    }

    /// <summary>The popped-out window's own Reattach: the main window shows it again and this one closes; with
    /// no main window open, it opens in a new one.</summary>
    public async Task ReattachOwnAsync()
    {
        if (Own is not { } key)
        {
            return;
        }
        // This window closes itself below, once the main window has what it held: never as the list says so first.
        _leavingOwn = true;
        var fresh = Mains == 0;
        if (fresh)
        {
            await _js.InvokeVoidAsync("sab.popOut.toMain", AddressNow); // while the click may still open a window
        }
        try
        {
            await _app.ReattachAsync(key, front: !fresh);
        }
        catch (ApiException error) when (error.Status == 404)
        {
            if (!fresh)
            {
                await _js.InvokeVoidAsync("sab.popOut.toMain", AddressNow); // the server forgot it (a restart)
            }
        }
        catch (ApiException error)
        {
            _leavingOwn = false;
            _notes.Error(error);
            return;
        }
        await CloseSelfAsync();
    }

    private async Task CloseSelfAsync()
    {
        if (BeforeClose is { } before)
        {
            await before();
        }
        await _js.InvokeVoidAsync("sab.popOut.closeSelf");
    }

    /// <summary>Show window: the popped-out window to the front.</summary>
    public async Task ShowAsync(string key)
    {
        await _js.InvokeVoidAsync("sab.popOut.show", key);
        try
        {
            await _app.ShowPopOutAsync(key);
        }
        catch (ApiException error) when (error.Status == 404)
        {
            // Back already.
        }
    }

    /// <summary>A link out of a popped-out window: the main window goes there (none open: a new one opens).</summary>
    public async Task ToMainAsync(string address)
    {
        var shown = false;
        try
        {
            shown = await _app.FrontAsync(address);
        }
        catch (ApiException)
        {
            // The server did not take it: a window of its own opens the address.
        }
        await _js.InvokeVoidAsync(shown ? "sab.popOut.focusOpener" : "sab.popOut.toMain", address);
    }

    /// <summary>A window this one opened was closed by the user: its page or table shows here again.</summary>
    [JSInvokable]
    public async Task WindowClosedAsync(string key)
    {
        try
        {
            await _app.ReattachAsync(key, front: false, closed: true);
        }
        catch (ApiException)
        {
            // Back already (Reattach closed it), or the server is away: its own wait brings it back.
        }
    }

    private void Take(PopOutsAnswer answer)
    {
        Popped = answer.Popped;
        Mains = answer.Mains;
        _held = _held || Popped.Any(e => e.Key == Own && e.Connected);
    }

    // What this window holds and where it is now: said as its socket opens and as it moves.
    private async Task SayOwnAsync()
    {
        if (Own is { } key && _live.Connected)
        {
            await _live.SendAsync(JsonSerializer.Serialize(new { type = Said, key, name = _ownName ?? key, address = AddressNow }));
        }
    }

    // An event handler returns nothing: the work goes on as a Task of its own.
    private void OnSocket() => _ = SayOwnAsync();

    private void OnMoved(object? sender, LocationChangedEventArgs e)
    {
        _ = SayOwnAsync();
        Changed?.Invoke();
    }

    private void OnNotice(Notice notice)
    {
        switch (notice.Type)
        {
            case ListNotice:
                _ = ListedAsync(notice.Body.Deserialize<PopOutsAnswer>(ApiClient.Json));
                break;
            case ShowNotice when notice.Text("key") == Own:
                _ = _js.InvokeVoidAsync("sab.popOut.focusSelf");
                break;
            case "grid_closed" when Own is { } mine && mine == PopOutKeys.TableKey(notice.Text("grid") ?? string.Empty):
                _ = ReattachOwnAsync(); // its table closed: nothing is left for this window to hold
                break;
            case OpenNotice when Own is null && notice.Text("key") is { } key:
                _ = _js.InvokeAsync<bool>("sab.popOut.open", key, notice.Text("address") ?? string.Empty, _self);
                break;
            case FrontNotice when Own is null && notice.Text("address") is { } address:
                _nav.NavigateTo(address);
                break;
            default:
                break;
        }
    }

    private async Task ListedAsync(PopOutsAnswer? answer)
    {
        if (answer is null)
        {
            return;
        }
        var held = _held;
        var before = Popped;
        Take(answer);
        // A window this one opened whose key is back: let go of it (never mistaken for the next one's closing).
        foreach (var gone in before.Where(was => Own is null && Popped.All(e => e.Key != was.Key)))
        {
            await _js.InvokeVoidAsync("sab.popOut.close", gone.Key);
        }
        if (Own is { } own && held && !_leavingOwn && Popped.All(e => e.Key != own))
        {
            await CloseSelfAsync(); // brought back: this window is done
            return;
        }
        // Brought back while this window shows its placeholder: the page where it was in its own window.
        if (Own is null && answer.Reattached is { Kind: PopOutKeys.Page } back && PopOutKeys.PageKey(Here) == back.Key && back.Address != Here)
        {
            _nav.NavigateTo(back.Address, replace: true);
        }
        Changed?.Invoke();
        _screen.Touch();
    }

    private Dictionary<string, object?> ScreenPart()
    {
        var keys = PopOutKeys.Of(Here);
        var elsewhere = Popped.Where(e => e.Key != Own).ToList();
        return new()
        {
            ["pop_out"] = Own is null ? null : _ownName,
            ["popped_out"] = elsewhere.Count == 0 ? null : elsewhere.Select(e => e.Name).ToList(),
            ["placeholder"] = elsewhere.FirstOrDefault(e => keys.Contains(e.Key))?.Placeholder,
        };
    }

    public void Dispose()
    {
        _live.NoticeArrived -= OnNotice;
        _live.Changed -= OnSocket;
        _nav.LocationChanged -= OnMoved;
        _screen.Hide(this);
        _self?.Dispose();
    }
}
