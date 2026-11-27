using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Accounting;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Accounting;

public partial class TemplatesDialog : IDisposable
{
    private IReadOnlyList<string> _names = [];
    private bool _listed;
    private WorkbookTemplate? _current;
    private int _sheet;
    private string? _place;
    private Exception? _error;

    [Parameter]
    public EventCallback OnClose { get; set; }

    /// <summary>Statements and invoices… with the template shown (or none).</summary>
    [Parameter]
    public EventCallback<string?> OnStatements { get; set; }

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private AccountingClient Accounting { get; set; } = default!;

    [Inject]
    private SwissArmyBench.Web.Api.Files.FileChooser Files { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    private PreviewSheet? Shown => _current?.Preview.Sheets.ElementAtOrDefault(_sheet);

    /// <summary>The bound places' words, by their cell and by their place as written.</summary>
    private IReadOnlyDictionary<string, string> Marks =>
        (_current?.Bindings ?? [])
            .SelectMany(b => new[] { ((b.Place.Contains('!') ? b.Place.Split('!')[1] : b.Place).ToUpperInvariant(), Said(b)), (b.Place, Said(b)) })
            .GroupBy(p => p.Item1)
            .ToDictionary(g => g.Key, g => g.First().Item2);

    protected override Task OnInitializedAsync()
    {
        Live.NoticeArrived += OnNotice;
        return ListAsync();
    }

    // A template bound anywhere (another window, the agent): the list and the one shown read again.
    private void OnNotice(Notice notice)
    {
        if (notice.Type == "template_changed")
        {
            _ = InvokeAsync(async () =>
            {
                await ListAsync();
                StateHasChanged();
            });
        }
    }

    public void Dispose() => Live.NoticeArrived -= OnNotice;

    /// <summary>What fills a place, in a few words: the lines' columns, a column, the number, the date or the text.</summary>
    public static string Said(TemplateBinding b) => b.Kind == "table"
        ? $"lines: {string.Join(", ", b.Columns ?? [])}"
        : b.Value?.Column is { Length: > 0 } column ? column
        : b.Value?.Number == true ? "number"
        : b.Value?.Date == true ? "date"
        : $"\"{b.Value?.Text ?? string.Empty}\"";

    private TemplateBinding? Existing(string place) =>
        _current?.Bindings.FirstOrDefault(b => string.Equals(b.Place, place, StringComparison.OrdinalIgnoreCase));

    private async Task ListAsync()
    {
        try
        {
            _names = (await Accounting.TemplatesAsync()).Templates;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _listed = true;
    }

    private async Task ImportAsync()
    {
        var source = await Files.ChooseAsync("file", "Import a template: an existing workbook", null, "template");
        if (string.IsNullOrWhiteSpace(source))
        {
            return;
        }
        try
        {
            var made = await Accounting.ImportTemplateAsync(source);
            _ = Notes.SayAsync($"Imported {made.Name}");
            await ListAsync();
            Take(made);
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task ShowAsync(string name)
    {
        try
        {
            Take(await Accounting.ShowTemplateAsync(name));
            await ListAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private void Take(WorkbookTemplate template)
    {
        _current = template;
        _sheet = Math.Max(0, Math.Min(_sheet, template.Preview.Sheets.Count - 1));
        _place = null;
    }

    /// <summary>A cell clicked: its named range is its place, else Sheet!B3.</summary>
    private void Pick(string sheet, (string Cell, string? Named) picked) => _place = picked.Named ?? $"{sheet}!{picked.Cell}";

    private async Task BindAsync(Dictionary<string, object?> body)
    {
        if (_current is not { } current)
        {
            return;
        }
        body["name"] = current.Name;
        try
        {
            Take(await Accounting.BindAsync(body));
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }
}
