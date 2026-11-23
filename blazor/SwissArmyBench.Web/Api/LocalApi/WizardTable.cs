namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>One of the sandbox's tables New endpoint offers.</summary>
public sealed record WizardTable(string Name, long? Rows = null, string Data = "");
