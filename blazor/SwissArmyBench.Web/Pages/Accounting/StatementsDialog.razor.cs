using System.Globalization;
using System.Text.Json;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Accounting;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Accounting;

public partial class StatementsDialog
{
    // The plan shows the totals of at most this many columns.
    private const int MaxTotals = 5;

    private IReadOnlyList<string> _templates = [];
    private IReadOnlyList<string> _tables = [];
    private bool _loaded;
    private string _template = string.Empty;
    private string _data = string.Empty;
    private string _lines = string.Empty;
    private string _groupBy = string.Empty;
    private string _name = string.Empty;
    private string _start = string.Empty;
    private string _pattern = string.Empty;
    private DateOnly? _date;
    private bool _oneBook;
    private BuildPlan? _plan;
    private string? _dry;
    private int? _builtCount;
    private Exception? _error;

    [Parameter]
    public string? Template { get; set; }

    [Parameter]
    public EventCallback OnClose { get; set; }

    [Inject]
    private AccountingClient Accounting { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    private bool BySheet => _plan?.Files.FirstOrDefault()?.Sheet is not null;

    private IReadOnlyList<string> TotalColumns => (_plan?.Files ?? []).SelectMany(f => f.Totals.Keys).Distinct().Take(MaxTotals).ToList();

    // Build waits for a dry run of the request as it is now.
    private bool CanBuild => _dry is not null && _dry == Key(Request());

    private string BuildWord => _builtCount is { } n && CanBuild ? $"Build {n}" : "Build";

    protected override async Task OnInitializedAsync()
    {
        try
        {
            _templates = (await Accounting.TemplatesAsync()).Templates;
        }
        catch (ApiException)
        {
            _templates = [];
        }
        try
        {
            _tables = await Accounting.OpenTablesAsync();
        }
        catch (ApiException)
        {
            _tables = [];
        }
        _template = Template ?? _templates.FirstOrDefault() ?? string.Empty;
        _data = _tables.FirstOrDefault(t => Matches(t, "statement|invoice|header|part")) ?? _tables.FirstOrDefault() ?? string.Empty;
        _lines = _tables.FirstOrDefault(t => Matches(t, "line|item|cession")) ?? string.Empty;
        _loaded = true;
    }

    private static bool Matches(string table, string pattern) =>
        System.Text.RegularExpressions.Regex.IsMatch(table, pattern, System.Text.RegularExpressions.RegexOptions.IgnoreCase);

    private static string Money(double n) => n.ToString("N2", CultureInfo.CurrentCulture);

    private static string Key(IReadOnlyDictionary<string, object?> request) => JsonSerializer.Serialize(request, ApiClient.Json);

    private Dictionary<string, object?> Request()
    {
        var request = new Dictionary<string, object?>
        {
            ["template"] = _template,
            ["data"] = _data,
            ["group_by"] = WorkbookRules.Split(_groupBy),
            ["one_workbook"] = _oneBook,
        };
        if (_lines.Length > 0)
        {
            request["lines"] = _lines;
        }
        if (_name.Trim().Length > 0)
        {
            request["name"] = _name.Trim();
        }
        if (_start.Trim().Length > 0)
        {
            var start = double.TryParse(_start, NumberStyles.Float, CultureInfo.InvariantCulture, out var n) ? n : double.NaN;
            request["number"] = new Dictionary<string, object?> { ["start"] = double.IsNaN(start) ? _start.Trim() : start, ["pattern"] = _pattern.Trim().Length > 0 ? _pattern.Trim() : "{n}" };
        }
        if (_date is { } date)
        {
            request["date"] = date.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
        }
        return request;
    }

    private async Task BuildAsync(bool dryRun)
    {
        var asked = Request();
        var body = new Dictionary<string, object?>(asked) { ["dry_run"] = dryRun };
        try
        {
            _error = null;
            var done = await Accounting.BuildAsync(body);
            _plan = done;
            _dry = dryRun ? Key(asked) : null;
            _builtCount = dryRun ? done.Count : null;
            if (!dryRun)
            {
                _ = Notes.SayAsync($"Built {done.Count} in {done.Folder}");
            }
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task RegisterAsync()
    {
        try
        {
            await Accounting.RegisterAsync();
            _ = Notes.SayAsync("The register is open on the Tables page");
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }
}
