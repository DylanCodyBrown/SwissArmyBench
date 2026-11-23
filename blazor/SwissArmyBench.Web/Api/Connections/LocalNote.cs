namespace SwissArmyBench.Web.Api.Connections;

/// <summary>What works only on this computer, and what runs on a Function App or hosted Streamlit app instead (the amber note).</summary>
public sealed record LocalNote(string Key, string Reason, string Instead, string Words);
