using System.Text.Json.Serialization;

namespace SwissArmyBench.Web.Components;

/// <summary>A side of the page a pane is docked on (PaneDock's two zones).</summary>
[JsonConverter(typeof(JsonStringEnumConverter<DockSide>))]
public enum DockSide
{
    Left,
    Right,
}
