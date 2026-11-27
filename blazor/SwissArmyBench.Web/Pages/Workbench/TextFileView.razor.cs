using System.Text.Json;
using System.Text.RegularExpressions;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.Pages.Workbench.Docs;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

public partial class TextFileView
{
    // The preview follows typing this long after it stops.
    private const int SettleMs = 350;

    private const string FrameNote = "Drawn in a walled-off frame: scripts in the file run there, away from the app. Pictures, style sheets and scripts beside the file or on the web are not loaded: the frame loads nothing from this computer or the network.";

    private ElementReference _source;
    private ElementReference _preview;
    private MarkdownReader? _reader;
    private DiagramPreview? _diagram;
    private IJSObjectReference? _module;
    private IJSObjectReference? _link;
    private string _drawn = string.Empty;
    private string? _drawnFor;
    private string? _linkedFor;
    private CancellationTokenSource? _later;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private WorkbenchClient Workbench { get; set; } = default!;

    [Inject]
    private ThemeState Theme { get; set; } = default!;

    /// <summary>The file's text as the page knows it.</summary>
    [Parameter, EditorRequired]
    public string Text { get; set; } = string.Empty;

    [Parameter]
    public string? Path { get; set; }

    /// <summary>The tab's view: preview, split or source (the bar's toggle; the tab remembers it).</summary>
    [Parameter]
    public string View { get; set; } = TextFiles.Source;

    [Parameter]
    public EventCallback<string> OnTextChanged { get; set; }

    /// <summary>A block edited in place or a task box ticked: the new text, to be saved at once.</summary>
    [Parameter]
    public EventCallback<string> OnEditedInPlace { get; set; }

    /// <summary>A key the page acts on (save).</summary>
    [Parameter]
    public EventCallback<string> OnPageKey { get; set; }

    /// <summary>A link in the document to another file: its whole path.</summary>
    [Parameter]
    public EventCallback<string> OnOpenFile { get; set; }

    private TextFileKind? Kind => TextFiles.KindOf(Path);

    /// <summary>The view drawn: the tab's, and for a file with no preview its source.</summary>
    private string Shown => Kind is { HasPreview: true } && TextFiles.Views.Contains(View) ? View : TextFiles.Source;

    private bool Dark => Theme.Effective is "dark" or "hc-dark";

    /// <summary>What the preview says of itself: an HTML page's frame loads nothing beside the file.</summary>
    private string? Note => Kind?.Preview == "html" && OutsidePattern().IsMatch(_drawn) ? FrameNote : null;

    /// <summary>A chart spec that is not JSON yet: said, instead of an empty chart.</summary>
    private string? SpecProblem
    {
        get
        {
            try
            {
                using var read = JsonDocument.Parse(_drawn);
                return read.RootElement.ValueKind == JsonValueKind.Object ? null : "A chart's spec is a JSON object.";
            }
            catch (JsonException error)
            {
                return $"Line {(error.LineNumber ?? 0) + 1}: the spec is not JSON yet ({error.Message})";
            }
        }
    }

    protected override void OnInitialized() => Theme.Changed += Redraw;

    protected override void OnParametersSet()
    {
        // The file's text from outside (opened, reloaded, another tab's edit): drawn at once; typing waits (TypedAsync).
        if (_drawnFor != Text && _later is null)
        {
            (_drawn, _drawnFor) = (Text, Text);
        }
    }

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        // Split view: the preview scrolls with its source (linked once both are drawn; again when the view changes).
        var wanted = Shown == TextFiles.Split ? $"{Path}|split" : null;
        if (wanted == _linkedFor)
        {
            return;
        }
        _linkedFor = wanted;
        await UnlinkAsync();
        if (wanted is not null)
        {
            _module ??= await Js.InvokeAsync<IJSObjectReference>("import", "./js/documents.js");
            _link = await _module.InvokeAsync<IJSObjectReference>("link", _source, _preview);
        }
    }

    private async Task TypedAsync(string text)
    {
        await OnTextChanged.InvokeAsync(text);
        Settle();
        _later = new CancellationTokenSource();
        var token = _later.Token;
        try
        {
            await Task.Delay(SettleMs, token);
            _later = null;
            (_drawn, _drawnFor) = (text, text);
            StateHasChanged();
        }
        catch (OperationCanceledException)
        {
            // typing went on
        }
    }

    private async Task KeyAsync(EditorKey key)
    {
        await OnTextChanged.InvokeAsync(key.Text);
        if (key.Name is "save" or "saveAs")
        {
            await OnPageKey.InvokeAsync(key.Name);
        }
    }

    /// <summary>The reader changed one block (or ticked a box): the page takes the text and saves it.</summary>
    private async Task EditedAsync(string text)
    {
        (_drawn, _drawnFor) = (text, text);
        await OnEditedInPlace.InvokeAsync(text);
    }

    /// <summary>A diagram's mistake marked on its line in the source beside it (Split view), or the mark cleared.</summary>
    private async Task DiagramProblemAsync(DiagramProblem? problem)
    {
        if (Shown != TextFiles.Split)
        {
            return;
        }
        _module ??= await Js.InvokeAsync<IJSObjectReference>("import", "./js/documents.js");
        await _module.InvokeVoidAsync("problem", _source, problem?.Line ?? 0, problem?.Message ?? string.Empty);
    }

    /// <summary>The diagram is drawn (its preview shown, its text without a mistake).</summary>
    public bool DiagramDrawn => _diagram?.Drawn == true;

    /// <summary>The block being edited in place written back (before the page saves or the view changes).</summary>
    public Task CommitAsync() => _reader?.CommitAsync() ?? Task.CompletedTask;

    /// <summary>The diagram's drawn picture saved beside its file: svg or png. What the server answered, or why not.</summary>
    public async Task<SavedPicture> SavePictureAsync(string format)
    {
        if (Path is not { } path || _diagram is not { } diagram)
        {
            throw new InvalidOperationException("Its preview is not shown: switch to Preview or Split first.");
        }
        _module ??= await Js.InvokeAsync<IJSObjectReference>("import", "./js/documents.js");
        var data = await _module.InvokeAsync<string>(format == "png" ? "pngOf" : "svgOf", diagram.Host);
        if (data.Length == 0)
        {
            throw new InvalidOperationException("The diagram is not drawn yet: fix what its preview says first.");
        }
        return await Workbench.ExportPictureAsync(path, format, data);
    }

    private void Redraw() => InvokeAsync(StateHasChanged);

    private void Settle()
    {
        _later?.Cancel();
        _later?.Dispose();
        _later = null;
    }

    private async Task UnlinkAsync()
    {
        if (_link is null)
        {
            return;
        }
        try
        {
            await _link.InvokeVoidAsync("stop");
            await _link.DisposeAsync();
        }
        catch (JSDisconnectedException)
        {
            // the page is going
        }
        _link = null;
    }

    [GeneratedRegex(@"\b(?:src|href)\s*=\s*[""']?(?!data:|#|mailto:|javascript:)[^""'\s>]", RegexOptions.IgnoreCase)]
    private static partial Regex OutsidePattern();

    public async ValueTask DisposeAsync()
    {
        Theme.Changed -= Redraw;
        Settle();
        await UnlinkAsync();
        if (_module is not null)
        {
            try
            {
                await _module.DisposeAsync();
            }
            catch (JSDisconnectedException)
            {
                // the page is going
            }
        }
    }
}
