using Bunit;

using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Components;

using Xunit;

namespace SwissArmyBench.Web.Tests;

public sealed class BusyAndDialogTests : AppTestContext
{
    [Fact]
    public void BusyCoversItsContentWithWordsAndCancel()
    {
        var busy = Render<Busy>(p => p
            .Add(x => x.IsBusy, true)
            .Add(x => x.Words, "Reading the made-up table…")
            .Add(x => x.OnCancel, () => { })
            .AddChildContent("<p>content</p>"));

        Assert.Equal("true", busy.Find(".busy-host").GetAttribute("aria-busy"));
        Assert.Contains("Reading the made-up table…", busy.Find(".busy-words").TextContent);
        Assert.Equal("Cancel", busy.Find(".busy-cover button").TextContent);
    }

    [Fact]
    public void NotBusyShowsOnlyItsContent()
    {
        var busy = Render<Busy>(p => p.Add(x => x.IsBusy, false).AddChildContent("<p>content</p>"));

        Assert.Empty(busy.FindAll(".busy-cover"));
        Assert.Equal("false", busy.Find(".busy-host").GetAttribute("aria-busy"));
    }

    [Fact]
    public void ADialogIsNamedByItsTitleAndEscapeClosesIt()
    {
        var closed = 0;
        var dialog = Render<AppDialog>(p => p
            .Add(x => x.Title, "Made-up question")
            .Add(x => x.OnClose, () => closed++));

        Assert.Equal("Made-up question", dialog.Find("[role=dialog]").GetAttribute("aria-label"));
        dialog.Find(".dialog-shade").KeyDown(new KeyboardEventArgs { Key = "Escape" });
        dialog.Find("button[aria-label=Close]").Click();

        Assert.Equal(2, closed);
    }
}
