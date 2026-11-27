using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;

namespace SwissArmyBench.Web.Pages.Workbench.Ide;

public partial class NewFileDialog : IDisposable
{
    // The check waits for typing to settle this long.
    private const int SettleMs = 300;

    private string _name = string.Empty;
    private string _folder = string.Empty;
    private string _connection = string.Empty;
    private string _variant = string.Empty;
    private string _makes = string.Empty;
    private string? _why;
    private bool _making;
    private CancellationTokenSource? _later;

    [Inject]
    private ScriptIdeClient Ide { get; set; } = default!;

    [Inject]
    private SwissArmyBench.Web.Api.Files.FileChooser Files { get; set; } = default!;

    /// <summary>A project is open: the folder is one inside it. None: a folder of this computer, its whole path.</summary>
    [Parameter]
    public bool HasProject { get; set; } = true;

    /// <summary>With no project open: the folder the dialog starts in (where the Workbench saves).</summary>
    [Parameter]
    public string StartFolder { get; set; } = string.Empty;

    /// <summary>The type picked in the dropdown.</summary>
    [Parameter, EditorRequired]
    public NewFileType Type { get; set; } = default!;

    /// <summary>The open project's folders ("" its top).</summary>
    [Parameter]
    public IReadOnlyList<string> Folders { get; set; } = [];

    /// <summary>The connections that run SQL, by name (a SQL file's Query from).</summary>
    [Parameter]
    public IReadOnlyList<string> Connections { get; set; } = [];

    [Parameter]
    public string ProjectName { get; set; } = string.Empty;

    [Parameter]
    public EventCallback OnClose { get; set; }

    /// <summary>Made: the new file, for the page to open.</summary>
    [Parameter]
    public EventCallback<NewFileMade> OnMade { get; set; }

    private NewFileRequest Request => new(
        Type.Id,
        _name.Trim(),
        _folder.Trim(),
        Type.AsksFor("connection") && _connection.Length > 0 ? _connection : null,
        _variant.Length > 0 ? _variant : null);

    protected override async Task OnInitializedAsync()
    {
        _name = Type.Suggested + Type.Ending;
        _folder = HasProject ? Type.Folder : StartFolder;
        _variant = Type.Variants is { Count: > 0 } variants ? variants[0].Id : string.Empty;
        await CheckAsync(CancellationToken.None);
    }

    /// <summary>Browse…: the folder picked with the app's file picker (the system's own dialog where it runs).</summary>
    private async Task BrowseAsync()
    {
        if (await Files.ChooseAsync("folder", "Where the new file goes", _folder.Trim().Length > 0 ? _folder.Trim() : null, "new-file") is { } folder)
        {
            _folder = folder;
            await CheckAsync(CancellationToken.None);
        }
    }

    private async Task LaterAsync()
    {
        Settle();
        _later = new CancellationTokenSource();
        var token = _later.Token;
        try
        {
            await Task.Delay(SettleMs, token);
            await CheckAsync(token);
        }
        catch (OperationCanceledException)
        {
            // typing went on
        }
    }

    /// <summary>Where the file would go, or the one sentence why it cannot be made (the server's own rule).</summary>
    private async Task CheckAsync(CancellationToken cancel)
    {
        try
        {
            var would = await Ide.CheckNewFileAsync(Request, cancel);
            (_makes, _why) = ($"Makes {(HasProject ? would.Relative : would.Path)}", null);
        }
        catch (ApiException error)
        {
            _why = error.Message;
        }
        catch (HttpRequestException)
        {
            _why = null; // Create says what is wrong
        }
    }

    private Task KeyAsync(KeyboardEventArgs e) => e.Key == "Enter" ? CreateAsync() : Task.CompletedTask;

    private async Task CreateAsync()
    {
        if (_making)
        {
            return;
        }
        _making = true;
        Settle();
        try
        {
            var made = await Ide.NewFileAsync(Request);
            await OnMade.InvokeAsync(made);
        }
        catch (ApiException error)
        {
            _why = error.Message;
        }
        finally
        {
            _making = false;
        }
    }

    private void Settle()
    {
        _later?.Cancel();
        _later?.Dispose();
        _later = null;
    }

    public void Dispose() => Settle();
}
