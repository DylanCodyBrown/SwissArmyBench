using System.Text;

namespace SwissArmyBench.Web.Pages.Workbench.Docs;

/// <summary>An SVG file's preview: the page the walled-off frame draws, the SVG as a picture (an img of its bytes),
/// so nothing in it runs, not even inside the frame.</summary>
public static class PictureFrame
{
    public static string Of(string svg, bool dark)
    {
        var data = Convert.ToBase64String(Encoding.UTF8.GetBytes(svg));
        var ground = dark ? "#1b2026" : "#ffffff";
        return "<!doctype html><html><head><meta charset=\"utf-8\"><style>html,body{height:100%;margin:0}"
            + $"body{{display:grid;place-items:center;background:{ground}}}img{{max-width:96%;max-height:96%}}</style></head>"
            + $"<body><img alt=\"The picture\" src=\"data:image/svg+xml;base64,{data}\"></body></html>";
    }
}
