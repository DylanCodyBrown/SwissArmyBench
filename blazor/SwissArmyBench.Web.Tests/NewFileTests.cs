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
    private static readonly NewFileType _python = new("python", "Python script", ".py", [".py"], "scripts", "scripts", "script", "python", "A module with a typed main().", "script");
    private static readonly NewFileType _sql = new("sql", "SQL file", ".sql", [".sql"], "scripts", "scripts", "sql", "sql", "Run file builds the open table named after the file.", "query", ["name", "folder", "connection"]);
    private static readonly NewFileType _json = new("json", "JSON", ".json", [".json"], "structures", "scripts", "structure", "json", "An empty object.", "data");
    private static readonly NewFileType _notebook = new("notebook", "Notebook", ".ipynb", [".ipynb"], string.Empty, "notebooks", "notebook", "notebook", "An empty notebook.", "notebook");
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
    public void Every_line_the_server_lists_can_be_picked()
    {
        // The server lists only what can be made now (with no project open, the types made in any folder).
        Assert.All(NewFileMenus.Entries(_types, _ => Task.CompletedTask), e => Assert.Null(e.Disabled));
    }

    [Fact]
    public void The_list_is_the_servers_data_and_a_type_of_the_projects_own_is_drawn_as_any_other()
    {
        // A type this page has never heard of (a project type's own, from its extension's mode): its line, its
        // icon, what its dialog asks. Nothing here names it.
        var gadget = new NewFileType("gadget", "Gadget", ".gadget.py", [".gadget.py"], "gadgets", "gadgets", "gadget", "sliders", "A made-up gadget.", "my_gadget", ["name"], [], false);
        NewFileType? picked = null;
        var button = Render<NewFileButton>(p => p.Add(b => b.Types, [.. _types, gadget]).Add(b => b.HasProject, true).Add(b => b.OnPick, t => picked = t));
        button.Find(".wb-top-new").Click();
        var last = button.FindAll("[role=menuitem]")[^1];
        Assert.Equal("Gadget (.gadget.py)", last.TextContent.Trim());
        last.Click();
        Assert.Same(gadget, picked);

        _server.Answer("POST /scripts/files/new", Made("gadgets/my_gadget.gadget.py", "gadget", made: false));
        var dialog = Render<NewFileDialog>(p => p.Add(d => d.Type, gadget).Add(d => d.HasProject, true));
        Assert.Equal("New Gadget", dialog.Find("[role=dialog]").GetAttribute("aria-label"));
        Assert.Equal("my_gadget.gadget.py", dialog.Find("input.new-file-name").GetAttribute("value"));
        Assert.Empty(dialog.FindAll("input.new-file-folder")); // it asks a name only
        Assert.Empty(dialog.FindAll("select"));
    }

    [Fact]
    public void One_type_is_one_plain_button_that_asks_its_name()
    {
        NewFileType? picked = null;
        var button = Render<NewFileButton>(p => p.Add(b => b.Types, [_notebook]).Add(b => b.OnPick, t => picked = t));
        Assert.Equal("New notebook", button.Find(".wb-top-new").TextContent.Trim());
        Assert.False(button.Find(".wb-top-new").HasAttribute("aria-haspopup"));
        button.Find(".wb-top-new").Click();
        Assert.Same(_notebook, picked);
    }

    [Fact]
    public async Task With_no_project_open_the_dialog_asks_a_folder_of_this_computerAsync()
    {
        _server.Answer("POST /scripts/files/new", """{"path": "/made/up/loose/script.py", "relative": "script.py", "type": "python", "kind": "script", "page": "scripts", "made": true}""");
        NewFileMade? made = null;
        var dialog = Render<NewFileDialog>(p => p.Add(d => d.Type, _python).Add(d => d.HasProject, false).Add(d => d.StartFolder, "/made/up/loose").Add(d => d.OnMade, m => made = m));

        Assert.Equal("Folder on this computer", dialog.Find("label.field:has(input.new-file-folder) > span").TextContent);
        Assert.Equal("/made/up/loose", dialog.Find("input.new-file-folder").GetAttribute("value"));
        Assert.Contains("Browse", dialog.Find(".new-file-browse").TextContent, StringComparison.Ordinal);
        Assert.Contains("No project is open", dialog.Find(".new-file-loose").TextContent, StringComparison.Ordinal);
        Assert.Empty(dialog.FindAll("datalist")); // no project's folders to offer
        dialog.WaitForAssertion(() => Assert.Equal("Makes /made/up/loose/script.py", dialog.Find(".new-file-check").TextContent));

        await dialog.Find(".new-file-create").ClickAsync(new MouseEventArgs());
        Assert.Equal("/made/up/loose/script.py", made?.Path);
        using var sent = JsonDocument.Parse(_server.Asked[^1].Body);
        Assert.Equal("/made/up/loose", sent.RootElement.GetProperty("folder").GetString()); // the folder's whole path
        Assert.Equal("script", sent.RootElement.GetProperty("name").GetString()?.Replace(".py", string.Empty, StringComparison.Ordinal));
    }

    [Fact]
    public async Task A_type_with_kinds_asks_which_and_sends_itAsync()
    {
        var diagram = new NewFileType("diagram", "Diagram", ".mmd", [".mmd", ".mermaid"], "docs/diagrams", "scripts", "text", "chart", "A Mermaid diagram.", "diagram",
            ["name", "folder", "variant"], [new("flowchart", "Flowchart (activity)"), new("class", "Class diagram"), new("sequence", "Sequence diagram")]);
        _server.Answer("POST /scripts/files/new", Made("docs/diagrams/diagram.mmd", "text", made: true));
        var dialog = Render<NewFileDialog>(p => p.Add(d => d.Type, diagram).Add(d => d.HasProject, true));
        Assert.Equal(["Flowchart (activity)", "Class diagram", "Sequence diagram"], dialog.FindAll("select.new-file-variant option").Select(o => o.TextContent));
        dialog.Find("select.new-file-variant").Change("sequence");
        await dialog.Find(".new-file-create").ClickAsync(new MouseEventArgs());
        using var sent = JsonDocument.Parse(_server.Asked[^1].Body);
        Assert.Equal("sequence", sent.RootElement.GetProperty("variant").GetString());
    }

    [Fact]
    public async Task Cancel_makes_nothingAsync()
    {
        _server.Answer("POST /scripts/files/new", Made("scripts/query.sql", "sql", made: false));
        var (closed, handed) = (0, 0);
        var dialog = Render<NewFileDialog>(p => p.Add(d => d.Type, _sql).Add(d => d.OnClose, () => closed++).Add(d => d.OnMade, _ => handed++));
        await dialog.Find(".new-file-cancel").ClickAsync(new MouseEventArgs());
        Assert.Equal((1, 0), (closed, handed));
        Assert.All(_server.Asked, asked => Assert.Contains("\"check\":true", asked.Body.Replace(" ", string.Empty, StringComparison.Ordinal), StringComparison.Ordinal)); // only the check: nothing written
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
    public void A_text_document_is_its_own_kind_of_tab()
    {
        var notes = new OpenDocument(1, false) { Path = "/made/up/shop/notes.md" };
        var todo = new OpenDocument(2, false) { Path = "/made/up/shop/TODO.TXT" };
        Assert.True(notes.IsText);
        Assert.True(todo.IsText);
        Assert.False(notes.IsCode); // nothing runs: no Python session, no Run file
        Assert.Equal("Document", notes.KindLabel);
        Assert.True(notes.CanRename);
        Assert.False(new OpenDocument(3, false) { Path = "/made/up/shop/load.py" }.IsText);
    }
}
