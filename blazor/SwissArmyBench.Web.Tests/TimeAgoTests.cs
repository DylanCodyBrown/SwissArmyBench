using Xunit;

namespace SwissArmyBench.Web.Tests;

/// <summary>A time as how long ago it was (a project card's Opened, a canvas card's Launched).</summary>
public sealed class TimeAgoTests
{
    private static readonly DateTimeOffset _now = new(2026, 11, 27, 12, 0, 0, TimeSpan.Zero);

    [Theory]
    [InlineData(20, "just now")]
    [InlineData(60, "1 minute ago")]
    [InlineData(3 * 60, "3 minutes ago")]
    [InlineData(60 * 60, "1 hour ago")]
    [InlineData(5 * 60 * 60, "5 hours ago")]
    [InlineData(30 * 60 * 60, "yesterday")]
    [InlineData(3 * 24 * 60 * 60, "3 days ago")]
    public void RecentTimesAreSaidInWords(int secondsAgo, string words) =>
        Assert.Equal(words, TimeAgo.Words(_now.AddSeconds(-secondsAgo), _now));

    [Fact]
    public void PastAMonthItIsTheDate()
    {
        var when = new DateTimeOffset(2026, 8, 14, 12, 0, 0, TimeSpan.Zero);

        Assert.Equal(when.ToLocalTime().ToString("d MMM yyyy"), TimeAgo.Words(when, _now));
    }

    [Fact]
    public void TheServersSecondsAreRead() =>
        Assert.Equal(new DateTimeOffset(2026, 11, 27, 12, 0, 0, TimeSpan.Zero), TimeAgo.FromSeconds(1795780800));
}
