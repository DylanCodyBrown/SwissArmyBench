namespace SwissArmyBench.Web;

/// <summary>A time as how long ago it was, in plain words ("3 minutes ago", "yesterday"); past a month the date
/// itself. A project card's Opened, a canvas card's Launched.</summary>
public static class TimeAgo
{
    private const int MinutesAnHour = 60;
    private const int HoursADay = 24;
    private const int DaysShown = 30;

    /// <summary>The whole time in this computer's own time ("24 Nov 2026, 09:30"): the hover's words.</summary>
    public static string Exact(DateTimeOffset when) => when.ToLocalTime().ToString("d MMM yyyy, HH:mm");

    public static string Words(DateTimeOffset when, DateTimeOffset now)
    {
        var ago = now - when;
        if (ago.TotalMinutes < 1)
        {
            return "just now";
        }
        if (ago.TotalMinutes < MinutesAnHour)
        {
            return Count((int)ago.TotalMinutes, "minute");
        }
        if (ago.TotalHours < HoursADay)
        {
            return Count((int)ago.TotalHours, "hour");
        }
        var days = (int)ago.TotalDays;
        if (days == 1)
        {
            return "yesterday";
        }
        return days <= DaysShown ? Count(days, "day") : when.ToLocalTime().ToString("d MMM yyyy");
    }

    /// <summary>A time the server gives as seconds since 1970.</summary>
    public static DateTimeOffset FromSeconds(double seconds) => DateTimeOffset.FromUnixTimeMilliseconds((long)(seconds * 1000));

    private static string Count(int count, string unit) => $"{count} {unit}{(count == 1 ? string.Empty : "s")} ago";
}
