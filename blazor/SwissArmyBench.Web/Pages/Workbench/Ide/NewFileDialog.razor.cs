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
    private string _makes = string.Empty;
    private string? _why;
    private bool _making;
    private CancellationTokenSource? _later;

    [Inject]
    private ScriptIdeClient Ide { get; set; } = default!;

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

    private bool IsSql => Type.Kind == "sql";

    private NewFileRequest Request => new(Type.Id, _name.Trim(), _folder.Trim(), IsSql && _connection.Length > 0 ? _connection : null);

    protected override async Task OnInitializedAsync()
    {
        _name = Type.Suggested + Type.Ending;
        _folder = Type.Folder;
        await CheckAsync(CancellationToken.None);
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
            (_makes, _why) = ($"Makes {would.Relative}", null);
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
