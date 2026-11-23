using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Apis;

namespace SwissArmyBench.Web.Pages.Apis;

public partial class ApisPage
{
    private ApiCards? _cards;
    private ApiExplorer? _explorer;
    private Exception? _error;

    [Inject]
    private ApisClient Apis { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [SupplyParameterFromQuery(Name = "name")]
    public string? NameParameter { get; set; }

    [SupplyParameterFromQuery(Name = "operation")]
    public string? OperationParameter { get; set; }

    protected override async Task OnParametersSetAsync()
    {
        await LoadAsync();
        await Js.InvokeVoidAsync("sab.setTitle", NameParameter ?? "APIs");
    }

    private async Task LoadAsync()
    {
        try
        {
            if (NameParameter is { } name)
            {
                _explorer = await Apis.ExploreAsync(name);
            }
            else
            {
                _cards = await Apis.CardsAsync();
            }
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }
}
