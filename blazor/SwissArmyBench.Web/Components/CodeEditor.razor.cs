using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Components;

public partial class CodeEditor
{
    private ElementReference _host;
    private IJSObjectReference? _module;
    private IJSObjectReference? _editor;
    private DotNetObjectReference<CodeEditor>? _self;
    private string _language = string.Empty;
    private bool _readOnly;

    // The text the editor holds as far as this side knows (its own last Changed, or the last value set): only a
    // different Value from the page is put in, so a render never takes back what was typed meanwhile.
    private string _known = string.Empty;

    // Focus asked for before Monaco was made (a cell just added): given once it is.
    private bool _focusWhenMade;

    // A line to show asked for before Monaco was made (a file just opened at a definition): shown once it is.
    private int? _revealWhenMade;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private ThemeState Theme { get; set; } = default!;

    /// <summary>The text it starts with; a later value from the page replaces the text (the cursor kept).</summary>
    [Parameter]
    public string Value { get; set; } = string.Empty;

    /// <summary>python, sql, dax, markdown, html, json, yaml, xml, toml...</summary>
    [Parameter]
    public string Language { get; set; } = "python";

    [Parameter]
    public bool ReadOnly { get; set; }

    /// <summary>A notebook cell's editor: as tall as its text, no scrollbar of its own. Else it fills its box.</summary>
    [Parameter]
    public bool Grow { get; set; }

    [Parameter]
    public int MinLines { get; set; } = 1;

    /// <summary>The editor's name for a screen reader ("Cell 3, Python").</summary>
    [Parameter]
    public string Label { get; set; } = "Code";

    /// <summary>The server's completion, signatures, hover and lint, asked with this context.</summary>
    [Parameter]
    public Func<IntelContext>? Intel { get; set; }

    [Parameter]
    public EventCallback<string> OnChange { get; set; }

    [Parameter]
    public EventCallback<EditorKey> OnKey { get; set; }

    [Parameter]
    public EventCallback OnFocus { get; set; }

    /// <summary>The Scripts page's IDE moves (F12, Shift+F12, F2, Shift+Alt+F) at the cursor; set, the editor offers
    /// them in its keys and its right-click menu.</summary>
    [Parameter]
    public EventCallback<IdeMove> OnIde { get; set; }

    /// <summary>The debugger's gutter: set, a click there toggles a breakpoint and a right click opens its menu.</summary>
    [Parameter]
    public EventCallback<GutterClick> OnGutter { get; set; }

    /// <summary>The ghost text providers the open project's mode declares (GitHub Copilot's), by language.</summary>
    [Parameter]
    public IReadOnlyList<SwissArmyBench.Web.Api.App.InlineProvider> Inline { get; set; } = [];

    /// <summary>The document a provider is told of (a script's text, or a notebook's cells and this one), or null.</summary>
    [Parameter]
    public Func<object?>? InlineDocument { get; set; }

    /// <summary>The lint's problems at warning or worse, as they change.</summary>
    [Parameter]
    public EventCallback<int> OnProblems { get; set; }

    protected override void OnInitialized() => Theme.Changed += OnThemeChanged;

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (firstRender)
        {
            _module = await Js.InvokeAsync<IJSObjectReference>("import", "./js/codeEditor.js");
            _self = DotNetObjectReference.Create(this);
            _language = Language;
            _readOnly = ReadOnly;
            _known = Value;
            var options = new { value = Value, language = Language, readOnly = ReadOnly, grow = Grow, minLines = MinLines, intel = Intel is not null, theme = Theme.Effective, ide = OnIde.HasDelegate, breakpoints = OnGutter.HasDelegate, inline = InlineDocument is null ? [] : Inline };
            _editor = await _module.InvokeAsync<IJSObjectReference>("create", _host, _self, options);
            if (_focusWhenMade)
            {
                await _editor.InvokeVoidAsync("focus");
            }
            if (_revealWhenMade is { } line)
            {
                await _editor.InvokeVoidAsync("revealLine", line);
            }
            return;
        }
        if (_editor is null)
        {
            return;
        }
        if (_known != Value)
        {
            _known = Value;
            await _editor.InvokeVoidAsync("setValue", Value);
        }
        if (_language != Language)
        {
            _language = Language;
            await _editor.InvokeVoidAsync("setLanguage", Language);
        }
        if (_readOnly != ReadOnly)
        {
            _readOnly = ReadOnly;
            await _editor.InvokeVoidAsync("setReadOnly", ReadOnly);
        }
    }

    /// <summary>The selected text, else the cursor's line (a script's Run selection).</summary>
    public async Task<string> SelectionAsync() => _editor is null ? string.Empty : await _editor.InvokeAsync<string>("selection");

    /// <summary>The text as it is now in the editor (typing not yet told).</summary>
    public async Task<string> TextAsync() => _editor is null ? Value : await _editor.InvokeAsync<string>("getValue");

    /// <summary>Text put in at the cursor, on a line of its own (a blade's line from the Blades pane).</summary>
    public async Task InsertAsync(string text)
    {
        if (_editor is not null)
        {
            await _editor.InvokeVoidAsync("insertLine", text);
        }
    }

    /// <summary>The cursor to a line, scrolled into view, with the focus (an error's In your code, a definition).</summary>
    public async Task RevealLineAsync(int line)
    {
        _revealWhenMade = _editor is null ? line : null;
        if (_editor is not null)
        {
            await _editor.InvokeVoidAsync("revealLine", line);
        }
    }

    public async Task FocusAsync()
    {
        _focusWhenMade = _editor is null;
        if (_editor is not null)
        {
            await _editor.InvokeVoidAsync("focus");
        }
    }

    [JSInvokable]
    public Task Changed(string text)
    {
        _known = text;
        return OnChange.InvokeAsync(text);
    }

    [JSInvokable]
    public Task Key(string name, string text)
    {
        _known = text;
        return OnKey.InvokeAsync(new EditorKey(name, text));
    }

    [JSInvokable]
    public Task Ide(string name, string text, int line, int column, string word)
    {
        _known = text;
        return OnIde.InvokeAsync(new IdeMove(name, text, line, column, word));
    }

    [JSInvokable]
    public Task Gutter(int line, bool menu, double x, double y) => OnGutter.InvokeAsync(new GutterClick(line, menu, x, y));

    public async Task SetBreakpointsAsync(IReadOnlyList<BreakpointMark> marks)
    {
        if (_editor is not null)
        {
            await _editor.InvokeVoidAsync("setBreakpoints", marks);
        }
    }

    /// <summary>The breakpoints' lines as edits have moved them, in line order.</summary>
    public async Task<IReadOnlyList<int>> BreakpointLinesAsync() =>
        _editor is null ? [] : (await _editor.InvokeAsync<int[]>("breakpointLines")).Order().ToList();

    /// <summary>The line a paused run stopped at, or null to clear it.</summary>
    public async Task SetExecutionLineAsync(int? line)
    {
        if (_editor is not null)
        {
            await _editor.InvokeVoidAsync("setExecutionLine", line ?? 0);
        }
    }

    public async Task<int> CursorLineAsync() => _editor is null ? 0 : await _editor.InvokeAsync<int>("cursorLine");

    /// <summary>The document ghost text is asked over, with this editor's text as it is now.</summary>
    [JSInvokable("InlineDocument")]
    public object? AskedDocument() => InlineDocument?.Invoke();

    [JSInvokable]
    public Task Focused() => OnFocus.InvokeAsync();

    [JSInvokable]
    public Task Linted(int problems) => OnProblems.InvokeAsync(problems);

    /// <summary>What codeEditor.js sends beside the text on each intelligence request.</summary>
    [JSInvokable]
    public IntelContext? IntelContext() => Intel?.Invoke();

    private void OnThemeChanged() => _ = InvokeAsync(async () =>
    {
        if (_module is not null)
        {
            await _module.InvokeVoidAsync("setTheme", Theme.Effective);
        }
    });

    public async ValueTask DisposeAsync()
    {
        Theme.Changed -= OnThemeChanged;
        if (_editor is not null)
        {
            try
            {
                await _editor.InvokeVoidAsync("dispose");
                await _editor.DisposeAsync();
            }
            catch (JSDisconnectedException)
            {
                // The page is closing: the editor goes with it.
            }
        }
        if (_module is not null)
        {
            await _module.DisposeAsync();
        }
        _self?.Dispose();
        GC.SuppressFinalize(this);
    }
}
