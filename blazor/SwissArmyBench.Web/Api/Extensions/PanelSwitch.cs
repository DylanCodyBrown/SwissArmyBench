namespace SwissArmyBench.Web.Api.Extensions;

/// <summary>A switch of an extension's panel.</summary>
public sealed record PanelSwitch(string Id, string Label, bool On, bool Disabled = false);
