using System.Net;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Components;

public partial class ErrorNote
{
    private bool _sent;

    [Inject]
    private ApiClient Api { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    /// <summary>What went wrong: an ApiException (the server's refusal) or any other exception; null shows nothing.</summary>
    [Parameter]
    public Exception? Error { get; set; }

    /// <summary>Words of the page's own, instead of an exception (a warning, a check that failed).</summary>
    [Parameter]
    public string? Words { get; set; }

    [Parameter]
    public bool Warning { get; set; }

    /// <summary>Try again: the work that failed, run once more.</summary>
    [Parameter]
    public EventCallback OnRetry { get; set; }

    [Parameter]
    public EventCallback OnClose { get; set; }

    private Refusal? Refusal => Error switch
    {
        ApiException api => api.Refusal,
        null when Words is not null => new Refusal(Words),
        null => null,
        _ => ApiClient.ReadRefusal(Error.Message, HttpStatusCode.InternalServerError) with { Details = Error.ToString() },
    };

    protected override void OnParametersSet() => _sent = false;

    private async Task RunFixAsync(Fix fix)
    {
        switch (fix.Action)
        {
            case "try_again":
                await OnRetry.InvokeAsync();
                break;
            case "set_variable":
                Nav.NavigateTo($"environment?at=settings&name={Uri.EscapeDataString(fix.Name ?? string.Empty)}");
                break;
            case "sign_in" or "open_settings":
                Nav.NavigateTo($"connections?name={Uri.EscapeDataString(fix.Connection ?? string.Empty)}");
                break;
            case "install" when fix.Command is not null:
                await Js.InvokeAsync<bool>("sab.copy", fix.Command);
                await Notes.SayAsync($"Copied the command: {fix.Command}");
                break;
            default:
                break;
        }
    }

    private async Task SendToAgentAsync()
    {
        var refusal = Refusal;
        if (refusal is null)
        {
            return;
        }
        await Api.PostAsync<object>("/agent/inbox", new { kind = "error", title = refusal.Error, text = refusal.Details ?? refusal.Error, note = refusal.Where ?? string.Empty });
        _sent = true;
    }

    private async Task CopyDetailsAsync()
    {
        if (await Js.InvokeAsync<bool>("sab.copy", Refusal?.Details ?? string.Empty))
        {
            await Notes.SayAsync("Copied.");
        }
    }
}
