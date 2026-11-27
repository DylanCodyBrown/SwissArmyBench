using System.Net;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Workbench.Docs;

public partial class MarkdownReader
{
    private ElementReference _host;
    private ElementReference _box;
    private IJSObjectReference? _module;
    private IJSObjectReference? _clicks;
    private DotNetObjectReference<MarkdownReader>? _self;
    private IReadOnlyList<MarkdownBlock> _blocks = [];
    private string? _readFor;
    private bool _read;
    private string? _problem;
    private int? _editing;
    private string _draft = string.Empty;
    private bool _focus;
    private Task _commit = Task.CompletedTask;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private WorkbenchClient Workbench { get; set; } = default!;

    /// <summary>The file's text as the page holds it.</summary>
    [Parameter, EditorRequired]
    public string Text { get; set; } = string.Empty;

    /// <summary>The file's whole path: pictures and links beside it are found from its folder.</summary>
    [Parameter]
    public string? Path { get; set; }

    /// <summary>The Read view: a click on a block edits it in place. Split view's preview only shows.</summary>
    [Parameter]
    public bool Editable { get; set; }

    [Parameter]
    public string Label { get; set; } = "Markdown";

    /// <summary>A block was edited or a task box ticked: the file's new text (only that block's characters changed).</summary>
    [Parameter]
    public EventCallback<string> OnEdited { get; set; }

    /// <summary>A link to another file was clicked: its whole path.</summary>
    [Parameter]
    public EventCallback<string> OnOpenFile { get; set; }

    /// <summary>The block being edited in place (null: none), for the page's screen state.</summary>
    public int? Editing => _editing;

    protected override async Task OnParametersSetAsync()
    {
        if (Text != _readFor)
        {
            await ReadAsync(Text);
        }
    }

    private async Task ReadAsync(string text)
    {
        _readFor = text;
        try
        {
            Show((await Workbench.MarkdownAsync(text)).Blocks);
        }
        catch (ApiException error)
        {
            _problem = error.Message;
        }
        catch (HttpRequestException)
        {
            _problem = "The file's blocks could not be read: the server did not answer.";
        }
    }

    private void Show(IReadOnlyList<MarkdownBlock> blocks)
    {
        (_blocks, _problem, _read) = (blocks, null, true);
        if (_editing is { } at && at >= blocks.Count)
        {
            _editing = null;
        }
    }

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (firstRender)
        {
            _self = DotNetObjectReference.Create(this);
            _module = await Js.InvokeAsync<IJSObjectReference>("import", "./js/documents.js");
            _clicks = await _module.InvokeAsync<IJSObjectReference>("reader", _host, _self);
        }
        if (_module is null)
        {
            return;
        }
        if (_focus && _editing is not null)
        {
            _focus = false;
            await _module.InvokeVoidAsync("editing", _box);
        }
        await _module.InvokeVoidAsync("highlight", _host);
    }

    /// <summary>A block clicked (or Enter on it): its source text in place.</summary>
    [JSInvokable]
    public Task Edit(int index) => InvokeAsync(() => EditAsync(index));

    private async Task EditAsync(int index)
    {
        if (!Editable || _editing == index)
        {
            return;
        }
        await CommitAsync(); // another block being edited is written back first
        if (_blocks.FirstOrDefault(b => b.Index == index) is not { } block)
        {
            return;
        }
        (_editing, _draft, _focus) = (block.Index, block.Text.Replace("\r\n", "\n"), true);
        StateHasChanged();
    }

    /// <summary>A task box clicked: ticked or cleared in the file (one character), then drawn from it.</summary>
    [JSInvokable]
    public Task Tick(int index, int task) => InvokeAsync(() => TickAsync(index, task));

    private async Task TickAsync(int index, int task)
    {
        try
        {
            var done = await Workbench.TickAsync(_readFor ?? Text, index, task);
            await ChangedAsync(done);
        }
        catch (ApiException error)
        {
            _problem = error.Message;
        }
        StateHasChanged();
    }

    /// <summary>A link to a file beside this one: opened by the page.</summary>
    [JSInvokable]
    public Task Follow(string href) => Resolve(href) is { } path ? InvokeAsync(() => OnOpenFile.InvokeAsync(path)) : Task.CompletedTask;

    private Task KeyAsync(KeyboardEventArgs e) => e.Key == "Escape" ? CommitAsync() : Task.CompletedTask;

    /// <summary>The block being edited written back into only its characters (unchanged: nothing sent on).</summary>
    public Task CommitAsync()
    {
        if (_editing is { } index)
        {
            _editing = null; // at once: Escape and the blur that follows it write back once
            _commit = WriteBackAsync(index);
        }
        return _commit; // one under way is waited for (a click on another block while this one is written)
    }

    private async Task WriteBackAsync(int index)
    {
        try
        {
            var before = _blocks.FirstOrDefault(b => b.Index == index)?.Text.Replace("\r\n", "\n");
            if (before is not null && _draft != before)
            {
                await ChangedAsync(await Workbench.EditBlockAsync(_readFor ?? Text, index, _draft));
            }
        }
        catch (ApiException error)
        {
            _problem = error.Message;
        }
        StateHasChanged();
    }

    private async Task ChangedAsync(MarkdownAnswer done)
    {
        _readFor = done.Text;
        Show(done.Blocks);
        if (done.Changed)
        {
            await OnEdited.InvokeAsync(done.Text);
        }
    }

    private string Html(MarkdownBlock block) => MarkdownText.ToHtml(block.Text, null, new MarkdownOptions(Tasks: true, Image: Image, Link: Link));

    /// <summary>A fenced block's code: what is between its first and last lines.</summary>
    private static string FencedCode(string text)
    {
        var lines = text.Replace("\r\n", "\n").Split('\n');
        var closed = lines.Length > 1 && lines[^1].TrimStart().StartsWith("```", StringComparison.Ordinal);
        return string.Join('\n', lines[1..(closed ? ^1 : lines.Length)]);
    }

    /// <summary>A picture: one beside the file is read through the server (pictures only); a web address is not
    /// loaded (nothing leaves the computer for a preview): its words link to it.</summary>
    private string? Image(string alt, string address)
    {
        var words = WebUtility.HtmlEncode(alt);
        if (IsWeb(address))
        {
            var href = WebUtility.HtmlEncode(address);
            return $"<a class=\"md-web-image\" href=\"{href}\" target=\"_blank\" rel=\"noopener noreferrer\" title=\"A picture on the web: not loaded here\">{(words.Length > 0 ? words : href)}</a>";
        }
        return Resolve(address) is { } path
            ? $"<img class=\"md-image\" alt=\"{words}\" loading=\"lazy\" src=\"{WebUtility.HtmlEncode(WorkbenchClient.PictureAddress(path))}\">"
            : null;
    }

    /// <summary>A link that is not a web address: a file beside this one (opened by the page), a place in this file
    /// (left as words), or mail (the system's).</summary>
    private string? Link(string inner, string address)
    {
        if (address.StartsWith("mailto:", StringComparison.OrdinalIgnoreCase))
        {
            return $"<a href=\"{WebUtility.HtmlEncode(address)}\">{inner}</a>";
        }
        return address.StartsWith('#') || address.Contains(':', StringComparison.Ordinal) || Resolve(address) is null
            ? $"<span class=\"md-anchor\">{inner}</span>"
            : $"<a href=\"{WebUtility.HtmlEncode(address)}\" data-file>{inner}</a>";
    }

    private static bool IsWeb(string address) =>
        address.StartsWith("http://", StringComparison.OrdinalIgnoreCase) || address.StartsWith("https://", StringComparison.OrdinalIgnoreCase);

    /// <summary>An address written relative to the file as a whole path (its #place and ?query dropped); null when
    /// the file has no folder yet or the address is not a path.</summary>
    private string? Resolve(string address)
    {
        var cut = address.IndexOfAny(['#', '?']);
        var relative = Uri.UnescapeDataString(cut >= 0 ? address[..cut] : address).Replace('\\', '/');
        if (Path is not { Length: > 0 } file || relative.Length == 0 || relative.Contains(':', StringComparison.Ordinal))
        {
            return null;
        }
        var folder = file.Replace('\\', '/');
        folder = folder[..Math.Max(0, folder.LastIndexOf('/'))];
        if (relative.StartsWith('/'))
        {
            return relative; // a whole path, as written
        }
        var parts = new List<string>(folder.Split('/'));
        foreach (var part in relative.Split('/'))
        {
            if (part == ".." && parts.Count > 1)
            {
                parts.RemoveAt(parts.Count - 1);
            }
            else if (part is not ("." or "" or ".."))
            {
                parts.Add(part);
            }
        }
        return string.Join('/', parts);
    }

    public async ValueTask DisposeAsync()
    {
        try
        {
            if (_clicks is not null)
            {
                await _clicks.InvokeVoidAsync("stop");
                await _clicks.DisposeAsync();
            }
            if (_module is not null)
            {
                await _module.DisposeAsync();
            }
        }
        catch (JSDisconnectedException)
        {
            // the page is going
        }
        _self?.Dispose();
    }
}
