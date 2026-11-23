using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Extensions;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Extensions;

public partial class ExtensionsPage
{
    private ExtensionList? _list;
    private Exception? _error;

    [Inject]
    private ExtensionsClient Extensions { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    protected override async Task OnInitializedAsync()
    {
        Live.NoticeArrived += OnNotice;
        await LoadAsync();
    }

    private async Task LoadAsync()
    {
        try
        {
            _list = await Extensions.ListAsync();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>The status in the classic words: a preinstalled extension that is installed says Preinstalled.</summary>
    private static string StatusWords(ExtensionCard card) => card.Status switch
    {
        "installed" when card.Preinstalled => "Preinstalled",
        "installed" => "Installed",
        "available" => "Available",
        "coming" => "Coming",
        _ => card.Status,
    };

    private Task InstallAsync(ExtensionCard card) => ChangeAsync(() => Extensions.InstallAsync(card.Id));

    private async Task RemoveAsync(ExtensionCard card)
    {
        if (await Dialogs.AskYesNoAsync($"Remove {card.Name}", $"Swiss Army Bench restarts without {card.Name}.", $"Remove {card.Name}", danger: true))
        {
            await ChangeAsync(() => Extensions.RemoveAsync(card.Id));
        }
    }

    private async Task ChangeAsync(Func<Task> change)
    {
        try
        {
            await change();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        await LoadAsync();
    }

    private void OnNotice(Notice notice)
    {
        if (notice.Type.StartsWith("extension", StringComparison.Ordinal))
        {
            _ = InvokeAsync(async () =>
            {
                await LoadAsync();
                StateHasChanged();
            });
        }
    }

    public void Dispose() => Live.NoticeArrived -= OnNotice;
}
