using System.Globalization;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Apis;
using SwissArmyBench.Web.Api.Files;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Apis;

public sealed partial class ApisPage : IDisposable
{
    private const int TypingPauseMilliseconds = 250;

    private ApiListing? _cards;
    private ApiExplorer? _explorer;
    private Exception? _error;
    private string _query = string.Empty;
    private IReadOnlyList<ApiHit>? _hits;
    private CancellationTokenSource? _typing;
    private string? _refreshing;
    private bool _applying;
    private (string Name, ApiDiff Diff)? _diff;
    private (string Name, string To)? _renaming;
    private (string Name, IReadOnlyList<ApiReference> References)? _deleting;

    [Inject]
    private ApisClient Apis { get; set; } = default!;

    [Inject]
    private FileChooser Files { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [SupplyParameterFromQuery(Name = "name")]
    public string? NameParameter { get; set; }

    [SupplyParameterFromQuery(Name = "add")]
    public string? AddParameter { get; set; }

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [SupplyParameterFromQuery(Name = "operation")]
    public string? OperationParameter { get; set; }

    protected override async Task OnParametersSetAsync()
    {
        _hits = null;
        _query = string.Empty;
        await LoadAsync();
        await Js.InvokeVoidAsync("sab.setTitle", AddParameter is not null ? "APIs › Add API" : NameParameter is { } name ? $"APIs › {name}" : "APIs");
    }

    private async Task LoadAsync()
    {
        try
        {
            if (AddParameter is not null)
            {
                return;
            }
            if (NameParameter is { } name)
            {
                _explorer = await Apis.ExploreAsync(name);
            }
            else
            {
                _cards = await Apis.ListingAsync();
                // An API read from an address and checked for changes is asked again as the page opens.
                foreach (var c in _cards.Apis.Where(c => c.Source is { Check: true, Kind: "address" }))
                {
                    await RefreshAsync(c.Name, true);
                }
            }
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private void AddedAsync(string name) => Nav.NavigateTo($"apis?name={Uri.EscapeDataString(name)}");

    private static string Count(int n, string word) => $"{n:N0} {word}{(n == 1 ? string.Empty : "s")}";

    private static string SourceWords(ApiCardInfo c)
    {
        var from = c.Source.Kind switch
        {
            "address" or "file" => c.Source.Address ?? string.Empty,
            "form" => "Made with the form",
            _ => "Pasted",
        };
        var read = c.Source.ReadAt is { } at && DateTimeOffset.TryParse(at, CultureInfo.InvariantCulture, DateTimeStyles.None, out var when)
            ? $" · read {when.ToLocalTime().ToString("g", CultureInfo.CurrentCulture)}"
            : string.Empty;
        return from + read;
    }

    private void SearchTyped(ChangeEventArgs e)
    {
        _query = e.Value?.ToString() ?? string.Empty;
        _typing?.Cancel();
        _typing = new CancellationTokenSource();
        var token = _typing.Token;
        _ = InvokeAsync(async () =>
        {
            try
            {
                await Task.Delay(TypingPauseMilliseconds, token);
            }
            catch (TaskCanceledException)
            {
                return;
            }
            await GuardAsync(async () => _hits = _query.Trim().Length > 0 ? (await Apis.SearchAsync(_query.Trim())).Results : null);
            StateHasChanged();
        });
    }

    /// <summary>Refresh: the document read again; what changed asked about (Apply, Not now), or said in one line.</summary>
    private async Task RefreshAsync(string name, bool quiet)
    {
        _refreshing = name;
        await GuardAsync(async () =>
        {
            var diff = (await Apis.RefreshAsync(name)).Diff;
            if (diff.Any)
            {
                _diff = (name, diff);
            }
            else if (!quiet)
            {
                _ = Notes.SayAsync($"{name} has not changed.");
            }
        });
        _refreshing = null;
    }

    private async Task ApplyAsync(string name)
    {
        _applying = true;
        await GuardAsync(async () =>
        {
            await Apis.ApplyRefreshAsync(name);
            _diff = null;
            _ = Notes.SayAsync($"{name} is up to date.");
            _cards = await Apis.ListingAsync();
        });
        _applying = false;
    }

    private Task CheckAsync(string name, bool on) => GuardAsync(() => Apis.CheckForChangesAsync(name, on));

    private async Task RenameAsync()
    {
        if (_renaming is not { } renaming)
        {
            return;
        }
        _renaming = null;
        await GuardAsync(async () =>
        {
            var done = await Apis.RenameAsync(renaming.Name, renaming.To);
            if (done.References.Count > 0)
            {
                _ = Notes.SayAsync($"{Count(done.References.Count, "place")} in code still name {renaming.Name}.");
            }
            _cards = await Apis.ListingAsync();
        });
    }

    private async Task CopyFolderAsync(ApiCardInfo c)
    {
        var file = c.File ?? string.Empty;
        var cut = Math.Max(file.LastIndexOf('/'), file.LastIndexOf('\\'));
        await Js.InvokeAsync<bool>("sab.copy", cut >= 0 ? file[..cut] : file);
        _ = Notes.SayAsync("Copied the folder's path");
    }

    private Task AskDeleteAsync(string name) => GuardAsync(async () => _deleting = (name, (await Apis.DeleteAsync(name, false)).References));

    private async Task DeleteAsync()
    {
        if (_deleting is not { } deleting)
        {
            return;
        }
        _deleting = null;
        await GuardAsync(async () =>
        {
            await Apis.DeleteAsync(deleting.Name, true);
            _cards = await Apis.ListingAsync();
        });
    }

    /// <summary>Make into blades: an older API connection made into the library's blades; its document read again
    /// from where it was made, else picked.</summary>
    private async Task MakeIntoBladesAsync(string name)
    {
        MadeBlades done;
        try
        {
            done = await Apis.MakeIntoBladesAsync(name, null);
        }
        catch (ApiException error) when (error.Refusal.Error.Contains("spec_path", StringComparison.Ordinal))
        {
            if (await Files.ChooseAsync("file", $"{name}'s OpenAPI document", null, "api", [".json", ".yaml", ".yml"]) is not { } file)
            {
                return;
            }
            done = await Apis.MakeIntoBladesAsync(name, file);
        }
        catch (ApiException error)
        {
            _error = error;
            return;
        }
        _ = Notes.SayAsync($"{name} is blades now: its API blade and {done.WebCalls.Count} web calls.");
        await LoadAsync();
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

    public void Dispose()
    {
        _typing?.Cancel();
        _typing?.Dispose();
    }
}
