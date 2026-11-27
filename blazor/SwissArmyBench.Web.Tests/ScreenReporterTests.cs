using System.Text.Json;

using Bunit;

using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Layout;
using SwissArmyBench.Web.Pages.Grids;
using SwissArmyBench.Web.State;

using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>
/// What a window shows, told to the server for the agent's app_screen: the reporter gathers many changes into one
/// report, sends only when the state differs from the last one sent, sends it whole again when the socket opens
/// again, and lets go as it closes; a table's part says names and numbers, never a value.
/// </summary>
public sealed class ScreenReporterTests : AppTestContext
{
    private const int Wait = 40;
    private const int Settled = 400;
    private const int Tries = 100;
    private const string MadeUpValue = "Larkfield-Value-7731";

    private readonly BunitJSModuleInterop _socket;
    private string _table = "orders";
    private int _reads;

    public ScreenReporterTests()
    {
        _socket = JSInterop.SetupModule(invocation => invocation.Identifier == "sab.live");
        _socket.Setup<bool>("send", _ => true).SetResult(true);
        _socket.SetupVoid("stop", _ => true).SetVoidResult();
        JSInterop.SetupModule("./js/screen.js").Mode = JSRuntimeMode.Loose;
    }

    private List<JsonElement> Sent() =>
        _socket.Invocations["send"]
            .Select(sent => JsonDocument.Parse((string)sent.Arguments[0]!).RootElement.Clone())
            .ToList();

    /// <summary>The reporter draws nothing, so nothing renders to wait on: the check is tried until it holds.</summary>
    private static async Task SettlesAsync(Action check)
    {
        for (var tries = 0; tries < Tries; tries++)
        {
            try
            {
                check();
                return;
            }
            catch (Xunit.Sdk.XunitException)
            {
                await Task.Delay(Wait, Xunit.TestContext.Current.CancellationToken);
            }
        }
        check();
    }

    private Dictionary<string, object?> Part()
    {
        _reads++;
        return new() { ["table"] = new Dictionary<string, object?> { ["name"] = _table }, ["tab"] = null };
    }

    private async Task<IRenderedComponent<ScreenReporter>> OpenedAsync(bool connected = true)
    {
        var live = Get<LiveUpdates>();
        await live.StartAsync();
        if (connected)
        {
            live.Opened();
        }
        Get<ScreenState>().Show(this, Part);
        var reporter = Render<ScreenReporter>(parameters => parameters.Add(r => r.WaitMs, Wait));
        if (connected)
        {
            await SettlesAsync(() => Assert.Single(Sent()));
        }
        return reporter;
    }

    [Fact]
    public async Task ManyChangesAreOneReportAsync()
    {
        var reporter = await OpenedAsync();
        var screen = Get<ScreenState>();
        var readsBefore = _reads;

        _table = "customers";
        for (var change = 0; change < 25; change++)
        {
            screen.Touch();
        }

        await SettlesAsync(() => Assert.Equal(2, Sent().Count));
        await Task.Delay(Settled, Xunit.TestContext.Current.CancellationToken);
        Assert.Equal(2, Sent().Count);
        Assert.Equal(readsBefore + 1, _reads); // the page's reader ran once for the 25 changes
        var report = Sent()[1];
        Assert.Equal("screen", report.GetProperty("type").GetString());
        Assert.Equal("customers", report.GetProperty("state").GetProperty("table").GetProperty("name").GetString());
    }

    [Fact]
    public async Task NothingIsSentWhenNothingChangedAsync()
    {
        await OpenedAsync();
        var screen = Get<ScreenState>();

        screen.Touch();
        await Task.Delay(Settled, Xunit.TestContext.Current.CancellationToken);
        screen.Touch();
        await Task.Delay(Settled, Xunit.TestContext.Current.CancellationToken);

        Assert.Single(Sent());
    }

    [Fact]
    public async Task WhatTheWindowSaysAndThePagesPartAreOneStateAsync()
    {
        var reporter = await OpenedAsync();

        await reporter.InvokeAsync(() => reporter.Instance.Seen("""{"page":"tables","width":1280,"focused":true,"dialogs":["Keep rows"],"tab":{"title":"from the window"}}"""));

        await SettlesAsync(() => Assert.Equal(2, Sent().Count));
        var state = Sent()[1].GetProperty("state");
        Assert.Equal("tables", state.GetProperty("page").GetString());
        Assert.Equal(1280, state.GetProperty("width").GetInt32());
        Assert.Equal("Keep rows", state.GetProperty("dialogs")[0].GetString());
        Assert.Equal("orders", state.GetProperty("table").GetProperty("name").GetString());
        // A part the page leaves empty keeps what the window said; a key with no value is not sent at all.
        Assert.Equal("from the window", state.GetProperty("tab").GetProperty("title").GetString());
        Assert.False(state.TryGetProperty("project", out _));

        // The same again from the window: nothing goes.
        await reporter.InvokeAsync(() => reporter.Instance.Seen("""{"page":"tables","width":1280,"focused":true,"dialogs":["Keep rows"],"tab":{"title":"from the window"}}"""));
        await Task.Delay(Settled, Xunit.TestContext.Current.CancellationToken);
        Assert.Equal(2, Sent().Count);
    }

    [Fact]
    public async Task AShutSocketSendsNothingAndAnOpenedOneGetsTheWholeStateAsync()
    {
        var reporter = await OpenedAsync(connected: false);
        var live = Get<LiveUpdates>();
        await Task.Delay(Settled, Xunit.TestContext.Current.CancellationToken);
        Assert.Empty(Sent());

        live.Opened();
        await SettlesAsync(() => Assert.Single(Sent()));

        // The server forgot this window when its socket closed: the same state goes once more as it opens again.
        live.Closed();
        live.Opened();
        await SettlesAsync(() => Assert.Equal(2, Sent().Count));
        Assert.Equal(Sent()[0].GetRawText(), Sent()[1].GetRawText());
    }

    [Fact]
    public async Task APageLeavingTakesItsPartAwayAndTheReporterLetsGoAsync()
    {
        var reporter = await OpenedAsync();
        var screen = Get<ScreenState>();

        screen.Hide(this);
        await SettlesAsync(() => Assert.Equal(2, Sent().Count));
        Assert.False(Sent()[1].GetProperty("state").TryGetProperty("table", out _));

        await reporter.Instance.DisposeAsync();
        Assert.Equal(0, Subscribers(screen, nameof(ScreenState.Changed)));
        Assert.Equal(0, Subscribers(Get<LiveUpdates>(), nameof(LiveUpdates.Changed)));
        screen.Touch();
        await Task.Delay(Settled, Xunit.TestContext.Current.CancellationToken);
        Assert.Equal(2, Sent().Count);
    }

    [Fact]
    public void ATablesPartSaysNamesAndNumbersNeverAValue()
    {
        using var filter = JsonDocument.Parse($$"""{"column":"region","op":"in","values":["{{MadeUpValue}}"],"value":"{{MadeUpValue}}"}""");
        using var sort = JsonDocument.Parse("""{"keys":[["amount","desc"],["id","asc"]]}""");
        using var rename = JsonDocument.Parse("""{"mapping":{"amt":"amount"}}""");
        var info = new GridInfo
        {
            Grid = "g1",
            Dataset = "orders",
            Columns = [new GridColumn { Name = "id", Type = "BIGINT" }, new GridColumn { Name = "region", Type = "VARCHAR" }],
            Steps =
            [
                new GridStep { Kind = "filter", Enabled = true, Params = filter.RootElement.Clone(), Description = $"Keep rows where region is one of ['{MadeUpValue}']" },
                new GridStep { Kind = "sort", Enabled = true, Params = sort.RootElement.Clone() },
                new GridStep { Kind = "rename", Enabled = false, Params = rename.RootElement.Clone() },
            ],
        };
        var selection = new GridSelection("cells", new SelectionDescriptor([[1, 3]], ["region"]), ["region"]);

        var part = TableScreen.Of(info, selection, 120, (0, 21));
        var json = JsonSerializer.Serialize(part);

        Assert.DoesNotContain(MadeUpValue, json, StringComparison.Ordinal);
        using var read = JsonDocument.Parse(json);
        var steps = read.RootElement.GetProperty("steps");
        Assert.Equal("in", steps[0].GetProperty("op").GetString());
        Assert.Equal("region", steps[0].GetProperty("columns")[0].GetString());
        Assert.Equal(["amount", "id"], steps[1].GetProperty("columns").EnumerateArray().Select(c => c.GetString()));
        Assert.Equal(["desc", "asc"], steps[1].GetProperty("directions").EnumerateArray().Select(c => c.GetString()));
        Assert.Equal("amt", steps[2].GetProperty("columns")[0].GetString());
        Assert.False(steps[2].GetProperty("enabled").GetBoolean());
        var picked = read.RootElement.GetProperty("selection");
        Assert.Equal(2, picked.GetProperty("rows")[0].GetProperty("first").GetInt64()); // from 1, as the grid counts
        Assert.Equal(4, picked.GetProperty("rows")[0].GetProperty("last").GetInt64());
        Assert.Equal(2, picked.GetProperty("column_numbers")[0].GetInt32());
        Assert.Equal(1, read.RootElement.GetProperty("showing").GetProperty("first").GetInt64());
        Assert.Equal(22, read.RootElement.GetProperty("showing").GetProperty("last").GetInt64());
        Assert.Equal(120, read.RootElement.GetProperty("rows").GetInt64());
    }
}
