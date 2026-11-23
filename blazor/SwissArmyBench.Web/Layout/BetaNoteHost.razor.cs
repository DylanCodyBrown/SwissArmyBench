using System.Globalization;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Settings;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Layout;

public partial class BetaNoteHost : IAsyncDisposable
{
    // The outline stands this many pixels outside the element's box (the classic betaNotes.ts).
    private const int OutlineGap = 3;

    private IJSObjectReference? _module;
    private BetaElement? _element;
    private string _text = string.Empty;
    private bool _attach;
    private bool _saving;
    private bool _opening;
    private Exception? _error;

    [Inject]
    private BetaState Beta { get; set; } = default!;

    [Inject]
    private SettingsClient Settings { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    protected override void OnInitialized() => Beta.Changed += Redraw;

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (firstRender)
        {
            _module = await Js.InvokeAsync<IJSObjectReference>("import", "./js/picture.js");
            await _module.InvokeVoidAsync("watch");
        }
    }

    private void Redraw() => _ = InvokeAsync(async () =>
    {
        if (Beta.Noting is null)
        {
            _text = string.Empty;
            _attach = false;
            _error = null;
            _element = null;
            _opening = false;
        }
        else if (!_opening)
        {
            _opening = true;
            _element = Beta.FromRightClick && _module is not null ? await _module.InvokeAsync<BetaElement?>("lastClicked") : null;
        }
        StateHasChanged();
    });

    private static string Outline(BetaBox box) => string.Create(CultureInfo.InvariantCulture,
        $"left: {box.X - OutlineGap}px; top: {box.Y - OutlineGap}px; width: {box.W + 2 * OutlineGap}px; height: {box.H + 2 * OutlineGap}px");

    private async Task KeyAsync(KeyboardEventArgs e)
    {
        if (e.Key == "Enter" && (e.CtrlKey || e.MetaKey))
        {
            await SaveAsync();
        }
    }

    private async Task SaveAsync()
    {
        if (_text.Trim().Length == 0 || Beta.Noting is not { } fallback)
        {
            return;
        }
        _saving = true;
        try
        {
            var place = _element ?? fallback;
            var page = Nav.ToBaseRelativePath(Nav.Uri).Split('?', '#')[0];
            // The picture leaves the note's own dialog out (the classic hides it while it is drawn).
            var picture = _attach && _module is not null ? await _module.InvokeAsync<string>("picture", ".dialog-shade") : null;
            await Settings.NoteAsync(new
            {
                text = _text,
                page = $"blazor/{(page.Length == 0 ? "home" : page)}",
                window = "blazor",
                element = new { tag = place.Tag, role = place.Role, name = place.Name, text = place.Text, path = place.Path, box = place.Box },
                attach_picture = _attach ? true : (bool?)null,
                picture,
            });
            Beta.NoteDone();
            _ = Notes.SayAsync("Saved");
        }
        catch (ApiException error)
        {
            _error = error;
        }
        finally
        {
            _saving = false;
        }
    }

    public async ValueTask DisposeAsync()
    {
        Beta.Changed -= Redraw;
        if (_module is not null)
        {
            await _module.DisposeAsync();
        }
        GC.SuppressFinalize(this);
    }
}
