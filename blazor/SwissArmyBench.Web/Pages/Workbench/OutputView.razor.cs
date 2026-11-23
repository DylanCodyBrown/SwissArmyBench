using System.Text;
using System.Text.Json;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

public partial class OutputView
{
    private const string PlotlyMime = "application/vnd.plotly.v1+json";

    // What an HTML output's frame may load: nothing from outside, no script (the frame's sandbox runs none either).
    private const string FramePolicy = "default-src 'none'; img-src data:; style-src 'unsafe-inline'";

    [Inject]
    private ThemeState Theme { get; set; } = default!;

    [Parameter, EditorRequired]
    public JsonElement Output { get; set; }

    /// <summary>A picture's address (a PNG or JPEG as it came; an SVG encoded), or null.</summary>
    private string? Picture
    {
        get
        {
            if (OutputReader.Data(Output, "image/png") is { } png)
            {
                return $"data:image/png;base64,{png.Trim()}";
            }
            if (OutputReader.Data(Output, "image/jpeg") is { } jpeg)
            {
                return $"data:image/jpeg;base64,{jpeg.Trim()}";
            }
            return OutputReader.Data(Output, "image/svg+xml") is { } svg
                ? $"data:image/svg+xml;base64,{Convert.ToBase64String(Encoding.UTF8.GetBytes(svg))}"
                : null;
        }
    }

    /// <summary>The HTML as the frame's page, in the theme's colours (a frame of another colour scheme would draw a
    /// white backdrop under a dark theme's light text).</summary>
    private string Framed(string html)
    {
        var dark = Theme.IsDark;
        var style = $"<style>:root{{color-scheme:{(dark ? "dark" : "light")}}}body{{margin:0;font:13px \"Segoe UI\",system-ui,sans-serif;"
            + $"color:{(dark ? "#e8ecef" : "#1c2228")};background:transparent}}table{{border-collapse:collapse}}"
            + $"th,td{{padding:3px 8px;border-bottom:1px solid {(dark ? "#343c45" : "#d5dbe1")};text-align:right}}th{{font-weight:600}}</style>";
        return $"<!doctype html><meta http-equiv=\"Content-Security-Policy\" content=\"{FramePolicy}\">{style}{html}";
    }
}
