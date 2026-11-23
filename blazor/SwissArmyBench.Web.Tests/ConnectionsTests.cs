using Bunit;

using Microsoft.Extensions.DependencyInjection;

using SwissArmyBench.Web.Api.Connections;
using SwissArmyBench.Web.Pages.Connections;
using SwissArmyBench.Web.State;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>The Connections page's own rules, as the classic connectionsWindow.ts says them: a password's one box,
/// a vault secret's variable, the words of a test and of the calls, a table's preview line, the slot line.</summary>
public sealed class ConnectionsTests : AppTestContext
{
    public ConnectionsTests()
    {
        Services.AddScoped<QueriesClient>();
        Services.AddScoped<ConnectionSlots>();
    }

    [Fact]
    public void APasswordBoxIsAVariableOnItsOwnOrATypedPassword()
    {
        var named = PasswordBox.Named("MADE_UP_PASSWORD");

        Assert.Equal("MADE_UP_PASSWORD", PasswordBox.ReferenceOnly(named));
        Assert.Null(PasswordBox.ReferenceOnly($"x{named}"));
        Assert.True(PasswordBox.NamesVariable($"x{named}"));
        Assert.False(PasswordBox.NamesVariable("plain words"));
        Assert.Equal("text", new PasswordBox("WAREHOUSE_PASSWORD").InputType);
        Assert.Equal("password", new PasswordBox("password").InputType);
        Assert.True(new PasswordBox("password") { Text = "typed" }.Typed);
        Assert.Equal("SALES_DB_PASSWORD", PasswordBox.VariableFor("Sales db", "password"));
        Assert.Equal("_1_SHOP_PASSWORD", PasswordBox.VariableFor("1 shop", "password"));
    }

    [Fact]
    public void AVaultSecretsVariableIsNamedAsInTheVault()
    {
        Assert.Equal("SqlPassword", VaultRow.EnvFor("SqlPassword"));
        Assert.Equal("Sql__Password", VaultRow.EnvFor("Sql--Password"));
        Assert.Equal("warehouse_password", VaultRow.EnvFor("warehouse-password"));
        Assert.Equal("_2fa", VaultRow.EnvFor("2fa"));
    }

    [Fact]
    public void TheWordsOfATestAndTheCalls()
    {
        Assert.Equal("a file of 16 bytes", ConnectionWords.Worked(new TestAnswer(Type: "pathlib.PosixPath", Found: "a file of 16 bytes")));
        Assert.Equal("2 tables, 1 column", ConnectionWords.Worked(new TestAnswer(Tables: 2, Columns: 1)));
        Assert.Equal("read A, B", ConnectionWords.Worked(new TestAnswer(Variables: ["A", "B"])));
        Assert.Equal("CSV file", ConnectionWords.Plain("A CSV file"));
        Assert.Equal("Tenant id", ConnectionWords.Words("tenant_id"));
        Assert.Equal("orders", ConnectionWords.Stem("/data/made up/orders.csv"));
        Assert.Equal("No calls yet", CallWords.Of(null));
        Assert.Equal("140 ms", CallWords.Ms(140));
        Assert.Equal("1.2 s", CallWords.Ms(1200));
        Assert.Equal("2 min", CallWords.Ms(120_000));
        Assert.Equal(
            "sab.connection(\"Made up\")  ·  %%sql \"Made up\"",
            ConnectionWords.InCode("Made up", "database", "duckdb"));
    }

    [Fact]
    public void ATablesPreviewSaysWhatItIs()
    {
        var rows = new TablePreview(["id"], [[System.Text.Json.JsonDocument.Parse("1").RootElement]], Table: "orders", Schema: "main", Total: 50);

        var preview = Render<TablePreviewView>(p => p.Add(x => x.Preview, rows));

        Assert.Contains("main.orders: the first 1 of 50 rows", preview.Markup);
        Assert.Equal("The table's first rows", preview.Find(".connection-preview").GetAttribute("aria-label"));
    }

    [Fact]
    public void TheSlotLineShowsOnlyWhileSomethingRunsUnlessAlways()
    {
        var resting = Render<SlotLine>(p => p.Add(x => x.Name, "Shop"));
        Assert.Empty(resting.FindAll("button"));
        resting.Instance.Dispose();

        var always = Render<SlotLine>(p => p.Add(x => x.Name, "Shop").Add(x => x.Always, true));

        Assert.Contains("Running 0 of 8", always.Find(".connection-slots-words").TextContent);
        Assert.Equal(1, Subscribers(Services.GetRequiredService<ConnectionSlots>(), "Changed"));
        always.Instance.Dispose();
        Assert.Equal(0, Subscribers(Services.GetRequiredService<ConnectionSlots>(), "Changed"));
    }
}
