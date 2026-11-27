using Bunit;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.Pages.Grids.Query;
using SwissArmyBench.Web.Pages.Grids.Tabs;
using SwissArmyBench.Web.Pages.Workbench;
using SwissArmyBench.Web.Pages.Workbench.Tabs;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>.sql files on the Scripts page and a tab's Rename… (the owner, 2026-11-24): the header line the dropdown
/// beside Run file writes, the table a run makes, the tab's menu and F2, and the Tables page's "+" and empty state
/// that go to a new SQL file (SQL is written only on the Scripts page).</summary>
public sealed class SqlFilesTests : AppTestContext
{
    [Fact]
    public void The_header_line_names_where_the_file_runs()
    {
        Assert.Equal("Warehouse", SqlHeader.Of("-- connection: Warehouse\nSELECT 1"));
        Assert.Equal("Finance Captive", SqlHeader.Of("-- a note\n--  Connection :  Finance Captive  \nSELECT 1"));
        Assert.Null(SqlHeader.Of("SELECT 1"));
        Assert.Null(SqlHeader.Of("SELECT 1;\n-- connection: Warehouse"));
        Assert.Null(SqlHeader.Of("-- connection:\nSELECT 1"));
    }

    [Fact]
    public void The_dropdown_writes_replaces_and_takes_away_the_header()
    {
        Assert.Equal("-- connection: Warehouse\nSELECT 1", SqlHeader.With("SELECT 1", "Warehouse"));
        Assert.Equal("-- connection: B\nSELECT 1", SqlHeader.With("-- connection: A\nSELECT 1", "B"));
        Assert.Equal("SELECT 1", SqlHeader.With("-- connection: A\nSELECT 1", null));
        Assert.Equal("SELECT 1", SqlHeader.With("SELECT 1", ""));
        Assert.Equal("-- connection: B\r\nSELECT 1\r\nFROM t", SqlHeader.With("SELECT 1\r\nFROM t", "B"));
    }

    [Theory]
    [InlineData("/made/up/scripts/orders_by_month.sql", "orders_by_month")]
    [InlineData("C:\\made\\up\\Orders by month.SQL", "Orders_by_month")]
    [InlineData(null, "query")]
    public void A_run_makes_the_table_named_after_the_file(string? path, string table) => Assert.Equal(table, SqlHeader.TableOf(path));

    [Fact]
    public void A_sql_file_is_its_own_kind_of_document()
    {
        var saved = new OpenDocument(1, false) { Path = "/made/up/q.sql" };
        Assert.True(saved.IsSql);
        Assert.False(saved.IsCode); // no Python session
        Assert.Equal("SQL file", saved.KindLabel);
        Assert.Equal("q.sql", saved.Title); // every document is a named file: there is no untitled one
        Assert.True(saved.CanRename);
    }

    [Fact]
    public void A_tabs_menu_has_rename_with_F2_and_a_blade_renames_elsewhere()
    {
        var split = new MenuEntry("Split right", "splitRight", () => Task.CompletedTask);
        var collaborate = new MenuEntry("Collaborate", "chat", () => Task.CompletedTask);
        var renamed = 0;
        var script = TabMenus.Entries(new OpenDocument(1, false) { Path = "/made/up/load.py" }, split, split, () => { renamed++; return Task.CompletedTask; }, () => Task.CompletedTask, collaborate);
        var rename = Assert.Single(script, e => e.Label == "Rename…");
        Assert.Equal("F2", rename.Keys);
        Assert.Null(rename.Disabled);
        rename.Run();
        Assert.Equal(1, renamed);
        Assert.Equal(["Split right", "Split right", "-", "Rename…", "Collaborate", "Close"], script.Select(e => e.Label));

        var blade = TabMenus.Entries(new OpenDocument(2, false) { Blade = "orders" }, split, split, () => Task.CompletedTask, () => Task.CompletedTask, collaborate);
        Assert.Equal(TabMenus.RenameElsewhere, blade.Single(e => e.Label == "Rename…").Disabled);
    }

    [Fact]
    public void F2_on_a_focused_tab_asks_to_rename_it()
    {
        var layout = new TabLayout();
        layout.Add(7);
        var docs = new Dictionary<int, OpenDocument> { [7] = new(7, false) { Path = "/made/up/orders.sql" } };
        int? asked = null;
        RenderFragment<OpenDocument> none = _ => _ => { };
        var view = Render<GroupView>(p => p
            .Add(x => x.Group, layout.Focused)
            .Add(x => x.Documents, docs)
            .Add(x => x.Content, none)
            .Add(x => x.Controls, none)
            .Add(x => x.OnRename, key => asked = key));

        Assert.Contains("orders.sql", view.Find(".wb-tab .tab-label").TextContent);
        view.Find(".wb-tabs").KeyDown(new KeyboardEventArgs { Key = "F2" });
        Assert.Equal(7, asked);
    }

    [Fact]
    public void The_tables_pages_plus_opens_a_new_sql_file_on_the_scripts_page()
    {
        var tabs = Render<GridTabs>(p => p.Add(x => x.Tabs, Array.Empty<GridListItem>()));
        var plus = tabs.Find("a.new-tab");
        Assert.Equal("scripts?new=sql", plus.GetAttribute("href"));
        Assert.Equal("New query", plus.GetAttribute("aria-label"));
        Assert.Empty(tabs.FindAll(".tab-draft")); // no draft tab: SQL is written on the Scripts page
    }

    [Fact]
    public void With_no_table_open_the_page_offers_a_file_and_a_new_query_only()
    {
        var opened = 0;
        var empty = Render<TablesEmpty>(p => p.Add(x => x.OnOpenFile, () => { opened++; }));
        empty.WaitForElement(".error-note"); // the project's tables to fix asked of a server that is not there
        Assert.Equal("scripts?new=sql", empty.Find("a.tables-empty-query").GetAttribute("href"));
        empty.WaitForAssertion(() =>
        {
            if (opened == 0)
            {
                empty.Find("button.tables-empty-open").Click(); // again only if a render in flight took the first
            }

            Assert.Equal(1, opened);
        });
        Assert.Empty(empty.FindAll(".new-query-choice")); // no connection cards
    }
}
