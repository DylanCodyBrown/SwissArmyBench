namespace SwissArmyBench.Web.Navigation;

/// <summary>One of the rail's areas.</summary>
/// <param name="Area">Its id (the classic rail.ts's Area, app_navigate's word).</param>
/// <param name="Name">The name on the rail and in its tip.</param>
/// <param name="Icon">Its icon in <see cref="Components.IconSet"/>.</param>
/// <param name="Route">This app's address for it, under /blazor/.</param>
/// <param name="Classic">The classic front end's address for the same place.</param>
/// <param name="Kind">notebook or script: the area wears that kind's colour.</param>
/// <param name="Keys">A shortcut shown in its tip.</param>
public sealed record RailArea(
    string Area,
    string Name,
    string Icon,
    string Route,
    string Classic,
    string? Kind = null,
    string? Keys = null);
