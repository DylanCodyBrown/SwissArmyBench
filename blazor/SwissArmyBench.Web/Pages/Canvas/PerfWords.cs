using System.Globalization;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>The analyzer's sizes and times in words (the classic perfPage.ts size and ms).</summary>
public static class PerfWords
{
    private const double Kilo = 1e3;
    private const double Mega = 1e6;

    public static string Size(double n) => n >= Mega
        ? string.Create(CultureInfo.InvariantCulture, $"{n / Mega:0.0} MB")
        : n >= Kilo ? string.Create(CultureInfo.InvariantCulture, $"{n / Kilo:0.0} KB") : string.Create(CultureInfo.InvariantCulture, $"{n:0} B");

    public static string Ms(double n) => n >= Kilo
        ? string.Create(CultureInfo.InvariantCulture, $"{n / Kilo:0.00} s")
        : string.Create(CultureInfo.InvariantCulture, $"{CanvasGrid.Round(n):0} ms");
}
