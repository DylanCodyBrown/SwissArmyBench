using System.Text.Json;

using Bunit;

using Microsoft.AspNetCore.Components.Web;
using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Pages.Workbench;
using SwissArmyBench.Web.Pages.Workbench.Ide;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>New file on the Scripts page (the owner, 2026-11-27): the dropdown lists the server's file types and
/// hands a pick over; the dialog fills the ending in, checks the name as the server does, asks a SQL file's
/// connection and makes the file once.</summary>
public sealed class NewFileTests : AppTestContext
{
    private static readonly NewFileType _python = new("python", "Python script", ".py", [".py"], "scripts", "scripts", "script", "python", "A module with a typed main().", "untitled");
    private static readonly NewFileType _sql = new("sql", "SQL file", ".sql", [".sql"], "scripts", "scripts", "sql", "sql", "Run file builds the open table named after the file.", "query");
    private static readonly NewFileType _json = new("json", "JSON", ".json", [".json"], "structures", "scripts", "structure", "json", "An empty object.", "data");
    private static readonly NewFileType _notebook = new("notebook", "Notebook", ".ipynb", [".ipynb"], string.Empty, "notebooks", "notebook", "notebook", "An empty notebook.", "untitled");
    private static readonly IReadOnlyList<NewFileType> _types = [_python, _sql, _json, _notebook];

    private readonly CannedServer _server = new();

    public NewFileTests()
    {
        Services.AddScoped(_ => new HttpClient(_server) { BaseAddress = new Uri("http://127.0.0.1:9/") });
        Services.AddScoped<ScriptIdeClient>();
    }

    private static string Made(string relative, string kind, bool made) =>
        $$"""{"path": "/made/up/shop/{{relative}}", "relative": "{{relative}}", "type": "sql", "kind": "{{kind}}", "page": "scripts", "made": {{(made ? "true" : "false")}}}""";

    [Fact]
    public void The_dropdown_lists_every_type_and_hands_the_pick_over()
    {
        NewFileType? picked = null;
        var button = Render<NewFileButton>(p => p.Add(b => b.Types, _types).Add(b => b.HasProject, true).Add(b => b.OnPick, t => picked = t));
        Assert.Empty(button.FindAll("[role=menu]"));
        Assert.Contains("New file", button.Find(".wb-top-new").TextContent, StringComparison.Ordinal);
        Assert.Equal("menu", button.Find(".wb-top-new").GetAttribute("aria-haspopup"));

        button.Find(".wb-top-new").Click();
        var lines = button.FindAll("[role=menuitem]");
        Assert.Equal(["Python script (.py)", "SQL file (.sql)", "JSON (.json)", "Notebook (.ipynb)"], lines.Select(l => l.TextContent.Trim()));
        Assert.All(lines, l => Assert.False(l.HasAttribute("disabled")));

        lines[1].Click();
        Assert.Same(_sql, picked);
        Assert.Empty(button.FindAll("[role=menu]")); // a pick closes the list
    }

    [Fact]
    public void With_no_project_open_only_the_types_that_start_untitled_can_be_picked()
    {
        var entries = NewFileMenus.Entries(_types, project: false, _ => Task.CompletedTask);
        Assert.Null(entries[0].Disabled);
        Assert.Null(entries[1].Disabled);
        Assert.Equal(NewFileMenus.NeedsProject, entries[2].Disabled);
        Assert.Null(entries[3].Disabled);
        Assert.All(NewFileMenus.Entries(_types, project: true, _ => Task.CompletedTask), e => Assert.Null(e.Disabled));
    }

    [Fact]
    public void The_dialog_fills_the_ending_in_and_says_where_the_file_goes()
    {
        _server.Answer("POST /scripts/files/new", Made("scripts/query.sql", "sql", made: false));
        var dialog = Render<NewFileDialog>(p => p.Add(d => d.Type, _sql).Add(d => d.Folders, ["", "scripts", "scripts/etl"]).Add(d => d.Connections, ["Finance Captive", "Warehouse"]).Add(d => d.ProjectName, "shop"));

        Assert.Equal("New SQL file", dialog.Find("[role=dialog]").GetAttribute("aria-label"));
        Assert.Equal("query.sql", dialog.Find("input.new-file-name").GetAttribute("value"));
        Assert.Equal("scripts", dialog.Find("input.new-file-folder").GetAttribute("value"));
        Assert.Equal(["scripts", "scripts/etl"], dialog.FindAll("datalist option").Select(o => o.GetAttribute("value")));
        Assert.Equal(["Open tables (DuckDB)", "Finance Captive", "Warehouse"], dialog.FindAll("select.new-file-connection option").Select(o => o.TextContent));
        dialog.WaitForAssertion(() => Assert.Equal("Makes scripts/query.sql", dialog.Find(".new-file-check").TextContent));
        using var checkedBody = JsonDocument.Parse(_server.Asked[0].Body);
        Assert.True(checkedBody.RootElement.GetProperty("check").GetBoolean()); // the first look writes nothing
    }

    [Fact]
    public void Only_a_sql_file_asks_where_it_runs()
    {
        _server.Answer("POST /scripts/files/new", Made("structures/data.json", "structure", made: false));
        var dialog = Render<NewFileDialog>(p => p.Add(d => d.Type, _json).Add(d => d.Connections, ["Warehouse"]));
        Assert.Empty(dialog.FindAll("select.new-file-connection"));
        Assert.Equal("data.json", dialog.Find("input.new-file-name").GetAttribute("value"));
        Assert.Equal("structures", dialog.Find("input.new-file-folder").GetAttribute("value"));
    }

    [Fact]
    public async Task Create_sends_the_name_the_folder_and_the_connection_and_hands_the_file_backAsync()
    {
        _server.Answer("POST /scripts/files/new", Made("scripts/reports/orders_by_month.sql", "sql", made: true));
        NewFileMade? made = null;
        var dialog = Render<NewFileDialog>(p => p.Add(d => d.Type, _sql).Add(d => d.Connections, ["Warehouse"]).Add(d => d.OnMade, m => made = m));
        dialog.Find("input.new-file-name").Input("orders_by_month");
        dialog.Find("input.new-file-folder").Input("scripts/reports");
        dialog.Find("select.new-file-connection").Change("Warehouse");

        await dialog.Find("input.new-file-name").KeyDownAsync(new KeyboardEventArgs { Key = "Enter" });

        Assert.Equal("scripts/reports/orders_by_month.sql", made?.Relative);
        using var sent = JsonDocument.Parse(_server.Asked[^1].Body);
        Assert.Equal("sql", sent.RootElement.GetProperty("type").GetString());
        Assert.Equal("orders_by_month", sent.RootElement.GetProperty("name").GetString());
        Assert.Equal("scripts/reports", sent.RootElement.GetProperty("folder").GetString());
        Assert.Equal("Warehouse", sent.RootElement.GetProperty("connection").GetString());
        Assert.False(sent.RootElement.TryGetProperty("check", out _));
    }

    [Fact]
    public async Task A_taken_name_is_said_in_the_dialog_and_nothing_is_handed_backAsync()
    {
        // No answer canned: the server's refusal (here its 404's one sentence) is what the dialog says.
        var handed = 0;
        var dialog = Render<NewFileDialog>(p => p.Add(d => d.Type, _sql).Add(d => d.OnMade, _ => handed++));
        await dialog.Find(".new-file-create").ClickAsync(new MouseEventArgs());

        Assert.Equal(0, handed);
        var check = dialog.Find(".new-file-check");
        Assert.Contains("error", check.ClassList);
        Assert.Equal("Not here.", check.TextContent);
        Assert.False(dialog.Find(".new-file-create").HasAttribute("disabled")); // another name can be tried
    }

    [Fact]
    public void A_markdown_or_text_file_is_its_own_kind_of_tab()
    {
        var notes = new OpenDocument(1, false) { Path = "/made/up/shop/notes.md" };
        var todo = new OpenDocument(2, false) { Path = "/made/up/shop/TODO.TXT" };
        Assert.True(notes.IsText);
        Assert.True(todo.IsText);
        Assert.False(notes.IsCode); // nothing runs: no Python session, no Run file
        Assert.Equal("Text file", notes.KindLabel);
        Assert.True(notes.CanRename);
        Assert.False(new OpenDocument(3, false) { Path = "/made/up/shop/load.py" }.IsText);
    }
}
