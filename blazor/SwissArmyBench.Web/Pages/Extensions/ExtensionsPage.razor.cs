using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Extensions;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Extensions;

public partial class ExtensionsPage
{
    private readonly Dictionary<string, string> _said = [];
    private ExtensionListing? _list;
    private Exception? _error;
    private string? _busy;
    private bool _newing;
    private (ExtensionInfo Ext, string Question)? _asking;

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
        try
        {
            _list = await Extensions.CardsAsync();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private static string StatusWords(ExtensionInfo ext) => ext.Source == "folder" ? "Installed (folder)" : ext.Status switch
    {
        "builtin" => "Built in",
        "installed" => "Installed",
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

    /// <summary>Remove a folder extension: the server asks first (its question), then its folder goes to the trash.</summary>
    private async Task RemoveAsync(ExtensionInfo ext, bool confirmed)
    {
        _said.Remove(ext.Id);
        _busy = ext.Id;
        try
        {
            var answer = await Extensions.RemoveAsync(ext.Id, confirmed);
            if (answer.Confirm is { } question)
            {
                _asking = (ext, question);
            }
            else if (answer.Removed is not null)
            {
                await LoadAsync(); // gone at once, no restart
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
            await RemoveAsync(asking.Ext, true);
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

    private void OnNotice(Notice notice)
    {
        if (notice.Type is "extensions_changed")
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
        GC.SuppressFinalize(this);
    }
}
