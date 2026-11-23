namespace SwissArmyBench.Web.Api.App;

/// <summary>A rail area an extension that is on adds (GET /app/areas): its name, icon, page and footer mark.</summary>
public sealed record AreaInfo(string Area, string Name, string Icon, string? Panel = null, string? Mark = null);
