namespace SwissArmyBench.Web.Pages.Scm;

/// <summary>How long ago, in VS Code's words ("3 mins ago", "1 day ago").</summary>
public static class ScmTime
{
    private const double Minute = 60;
    private const double Hour = 3600;
    private const double Day = 86400;

    public static string Ago(DateTimeOffset then, DateTimeOffset now)
    {
        var s = Math.Max(1, Math.Round((now - then).TotalSeconds));
        static string Unit(double n, string one) => $"{n} {one}{(n == 1 ? string.Empty : "s")} ago";
        return s switch
        {
            < Minute => Unit(s, "sec"),
            < Hour => Unit(Math.Round(s / Minute), "min"),
            < Day => Unit(Math.Round(s / Hour), "hr"),
            < Day * 7 => Unit(Math.Round(s / Day), "day"),
            < Day * 30 => Unit(Math.Round(s / Day / 7), "wk"),
            < Day * 365 => Unit(Math.Round(s / Day / 30), "mo"),
            _ => Unit(Math.Round(s / Day / 365), "yr"),
        };
    }
}
