using System.Text.RegularExpressions;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Collaboration;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Layout.Collaboration;

public partial class CollabComposer
{
    private const string TooBigWords = "A picture is 5 MB at most.";

    /// <summary>The formatting bar: the composer's kind (collaboration.js FORMATS), its words, its mark, its keys.</summary>
    private static readonly IReadOnlyList<(string Kind, string Label, string Mark, string Keys)> _formats =
    [
        ("bold", "Bold", "<b>B</b>", "Ctrl+B"),
        ("italic", "Italic", "<i>I</i>", "Ctrl+I"),
        ("strike", "Strikethrough", "<s>S</s>", "Ctrl+Shift+X"),
        ("code", "Code", "<code>&lt;/&gt;</code>", "Ctrl+Shift+C"),
        ("block", "Code block", "<code>{ }</code>", "Ctrl+Alt+C"),
        ("link", "Link", "🔗", "Ctrl+K"),
        ("bullets", "Bulleted list", "•", "Ctrl+Shift+8"),
        ("numbers", "Numbered list", "1.", "Ctrl+Shift+7"),
        ("quote", "Quote", "❝", "Ctrl+Shift+9"),
        ("task", "Task list", "☐", "- [ ]"),
    ];

    private readonly List<CollabImage> _images = [];
    private List<CollabPick> _picks = [];
    private ElementReference _box;
    private IJSObjectReference? _module;
    private IJSObjectReference? _handle;
    private DotNetObjectReference<CollabComposer>? _self;
    private string _text = string.Empty;
    private char _popup;
    private int _typedLength;
    private int _index;
    private int _asked;
    private bool _sending;
    private string? _said;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private CollaborationClient Client { get; set; } = default!;

    [Inject]
    private CollaborationState State { get; set; } = default!;

    [Inject]
    private EmojiCatalog Emoji { get; set; } = default!;

    [Parameter]
    public string Label { get; set; } = "Message";

    [Parameter]
    public string Placeholder { get; set; } = "Write a note";

    /// <summary>The Markdown and its pictures: true once sent (the box is emptied).</summary>
    [Parameter, EditorRequired]
    public Func<string, IReadOnlyList<CollabImage>, Task<bool>> OnSend { get; set; } = default!;

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (firstRender)
        {
            _self = DotNetObjectReference.Create(this);
            _module = await Js.InvokeAsync<IJSObjectReference>("import", "./js/collaboration.js");
            _handle = await _module.InvokeAsync<IJSObjectReference>("composer", _box, _self);
            await _handle.InvokeVoidAsync("focus");
        }
    }

    private async Task FormatAsync(string kind)
    {
        if (_handle is not null)
        {
            await _handle.InvokeVoidAsync("format", kind);
        }
    }

    [JSInvokable("Typed")]
    public async Task TypedAsync(string value, int caret)
    {
        _text = value;
        var before = value[..Math.Clamp(caret, 0, value.Length)];
        if (MentionTyped().Match(before) is { Success: true } mention)
        {
            await ListAsync('@', mention.Groups[1].Value);
        }
        else if (EmojiTyped().Match(before) is { Success: true } emoji)
        {
            await ListAsync(':', emoji.Groups[1].Value);
        }
        else
        {
            await ClosePopupAsync();
        }
        StateHasChanged();
    }

    private async Task ListAsync(char popup, string typed)
    {
        _popup = popup;
        _typedLength = typed.Length + 1;
        _index = 0;
        if (popup == ':')
        {
            var found = await Emoji.MatchingAsync(typed);
            _picks = found.Select(e => new CollabPick($"{e.Emoji} {e.Name}", string.Empty, e.Emoji, "star")).ToList();
        }
        else
        {
            var asked = ++_asked;
            try
            {
                var found = await Client.ObjectsAsync(typed, State.Page);
                if (asked != _asked)
                {
                    return; // typed on since
                }
                _picks = CollabPicking.Of(State.PageObjects, found, typed).ToList();
            }
            catch (ApiException error)
            {
                _said = error.Message;
                _picks = [];
            }
        }
        if (_handle is not null)
        {
            await _handle.InvokeVoidAsync("setPopup", _picks.Count > 0);
        }
    }

    private async Task ClosePopupAsync()
    {
        if (_picks.Count == 0 && _popup == default)
        {
            return;
        }
        _picks = [];
        _popup = default;
        if (_handle is not null)
        {
            await _handle.InvokeVoidAsync("setPopup", false);
        }
    }

    [JSInvokable("PopupKey")]
    public async Task PopupKeyAsync(string key)
    {
        switch (key)
        {
            case "ArrowDown":
                _index = (_index + 1) % Math.Max(1, _picks.Count);
                break;
            case "ArrowUp":
                _index = (_index - 1 + _picks.Count) % Math.Max(1, _picks.Count);
                break;
            case "Enter" or "Tab":
                await PickAsync(_index);
                break;
            default:
                await ClosePopupAsync();
                break;
        }
        StateHasChanged();
    }

    private async Task PickAsync(int at)
    {
        if (at < 0 || at >= _picks.Count || _handle is null)
        {
            return;
        }
        var pick = _picks[at];
        var count = _typedLength;
        await ClosePopupAsync();
        await _handle.InvokeVoidAsync("replaceBefore", count, pick.Insert);
    }

    [JSInvokable("Send")]
    public Task SendFromKeyAsync() => SendAsync();

    private async Task SendAsync()
    {
        if (_sending || string.IsNullOrWhiteSpace(_text))
        {
            return;
        }
        _sending = true;
        StateHasChanged();
        try
        {
            if (await OnSend(_text, _images.ToList()) && _handle is not null)
            {
                _images.Clear();
                await _handle.InvokeVoidAsync("set", string.Empty);
            }
        }
        finally
        {
            _sending = false;
            StateHasChanged();
        }
    }

    [JSInvokable("Pasted")]
    public async Task PastedAsync(string type, string data)
    {
        _images.Add(new CollabImage(type, data));
        if (_handle is not null)
        {
            await _handle.InvokeVoidAsync("insert", $"![picture](sab-image:new-{_images.Count})");
        }
        StateHasChanged();
    }

    [JSInvokable]
    public void TooBig(string name)
    {
        _said = $"{name}: {TooBigWords}";
        StateHasChanged();
    }

    public async ValueTask DisposeAsync()
    {
        if (_handle is not null)
        {
            await _handle.InvokeVoidAsync("stop");
            await _handle.DisposeAsync();
        }
        if (_module is not null)
        {
            await _module.DisposeAsync();
        }
        _self?.Dispose();
    }

    // `@` at the start or after a space, then what is typed so far (no space: a person's login, an object's words).
    [GeneratedRegex(@"(?:^|\s)@([^\s@\[\]()]{0,40})$")]
    private static partial Regex MentionTyped();

    [GeneratedRegex(@"(?:^|\s):([a-z0-9_+\-]{2,20})$")]
    private static partial Regex EmojiTyped();
}
