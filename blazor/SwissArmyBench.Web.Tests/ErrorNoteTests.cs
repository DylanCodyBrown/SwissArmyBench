using Bunit;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Components;

using Xunit;

namespace SwissArmyBench.Web.Tests;

public sealed class ErrorNoteTests : AppTestContext
{
    [Fact]
    public void PlainWordsShowAsTheNote()
    {
        var note = Render<ErrorNote>(p => p.Add(x => x.Words, "The table is gone."));

        Assert.Contains("The table is gone.", note.Find(".error-note-what").TextContent);
        Assert.Equal("alert", note.Find(".error-note").GetAttribute("role"));
    }

    [Fact]
    public void ARefusalShowsWhereAndEachFixAsAButton()
    {
        var refusal = new Refusal("The connection did not answer.", "Made-up warehouse", [new Fix("Sign in", "sign_in")]);
        var note = Render<ErrorNote>(p => p.Add(x => x.Error, new ApiException(502, refusal, string.Empty)));

        Assert.Contains("Made-up warehouse", note.Find(".error-note-where").TextContent);
        Assert.Contains(note.FindAll(".error-note-fixes button"), b => b.TextContent == "Sign in");
    }

    [Fact]
    public void NothingShowsWithoutAnError()
    {
        var note = Render<ErrorNote>();

        Assert.Empty(note.FindAll(".error-note"));
    }

    [Fact]
    public void CloseIsNamedAndCallsBack()
    {
        var closed = false;
        var note = Render<ErrorNote>(p => p
            .Add(x => x.Words, "Made-up problem.")
            .Add(x => x.OnClose, () => closed = true));

        note.Find("button[aria-label=Close]").Click();

        Assert.True(closed);
    }
}
