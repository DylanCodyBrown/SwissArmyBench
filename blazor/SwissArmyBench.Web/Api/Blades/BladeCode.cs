namespace SwissArmyBench.Web.Api.Blades;

/// <summary>GET /blades/{name}/code: its file's code and stamp (an edit made outside changes the stamp).</summary>
public sealed record BladeCode(string Name, string Code, string Stamp, bool ReadOnly = false);
